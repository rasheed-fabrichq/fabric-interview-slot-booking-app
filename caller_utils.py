"""
Client for the calling system that places reminder calls to candidates.

This application does not dial anything itself. It POSTs a candidate's
number and a set of prompt variables to the calling system, which owns
the assistant, the SIP trunk and the call itself.

Configure in .env:

    CALLER_API_BASE_URL   default http://localhost:8000
    CALLER_API_PATH       default /api/v1/call/
    CALLER_PASS_KEY       sent as the x-pass-key header
    CALLER_API_KEY        optional; sent as Authorization if set
    CALLER_ASSISTANT_ID   the assistant to run
    CALLER_AGENT_NAME     the voice agent's name, e.g. Riya
    CALLER_COMPANY_NAME   the client, e.g. Kearney
    CALL_DISQUALIFICATION_RATE  spoken rate, e.g. "eighty percent"
    CALLER_PHONE_FORMAT   'national' (default) or 'e164'
"""
import json
import logging
import os
import urllib.error
import urllib.request

from speech_utils import number_to_words, time_to_words, datetime_to_words

logger = logging.getLogger(__name__)

# urllib rather than requests: this is a single POST, and the VM would
# otherwise need a new dependency installed.
DEFAULT_TIMEOUT_SECONDS = 20


def _cfg(key, default=''):
    """Read config from env at call time, after dotenv has loaded."""
    return os.environ.get(key, default)


# Maps a config key to its env variable and default. A per-job
# override, when present, wins over the env value.
CALL_SETTINGS = {
    'assistant_id': ('CALLER_ASSISTANT_ID', ''),
    'agent_type': ('CALLER_AGENT_TYPE', 'integrity_reminder'),
    'agent_name': ('CALLER_AGENT_NAME', 'Riya'),
    'company_name': ('CALLER_COMPANY_NAME', 'Kearney'),
    'disqualification_rate': ('CALL_DISQUALIFICATION_RATE', 'eighty percent'),
    'api_base_url': ('CALLER_API_BASE_URL', 'http://localhost:8000'),
}


def resolve_setting(key, job_config=None):
    """Value for one call setting: per-job override, else env default."""
    if job_config and job_config.get(key) not in (None, ''):
        return job_config[key]
    env_key, default = CALL_SETTINGS.get(key, (None, ''))
    return _cfg(env_key, default) if env_key else default


def get_call_endpoint(job_config=None):
    base = resolve_setting('api_base_url', job_config).rstrip('/')
    path = _cfg('CALLER_API_PATH', '/api/v1/call/')
    if not path.startswith('/'):
        path = '/' + path
    return base + path


def format_phone_for_api(e164_number):
    """Render a stored E.164 number the way the calling system wants.

    Numbers are stored as +919876543210. The API example shows a bare
    national number (9876543210), so that is the default; set
    CALLER_PHONE_FORMAT=e164 to send the full international form.
    """
    if not e164_number:
        return ''
    number = str(e164_number).strip()
    if _cfg('CALLER_PHONE_FORMAT', 'national').lower() == 'e164':
        return number
    # Strip a leading + and the Indian country code, leaving the
    # 10-digit national number.
    digits = number.lstrip('+')
    if digits.startswith('91') and len(digits) == 12:
        return digits[2:]
    return digits


def build_call_payload(candidate_name, phone_e164, job_name, slot_start,
                       slot_end, duration_minutes, now, user_id,
                       job_config=None):
    """Assemble the request body for one reminder call.

    job_config is the per-job override row, if the job has one; any
    value it does not set falls back to the env default.

    Every spoken value is converted to words here, because the voice
    agent reads these verbatim and TTS engines render bare digits
    unreliably.
    """
    # The spoken role defaults to the job's name, but a job can override
    # it -- an internal job title is not always what you want read out.
    role = (job_config or {}).get('role_name') or job_name

    return {
        'user_id': user_id,
        'assistant_id': resolve_setting('assistant_id', job_config),
        'agent_type': resolve_setting('agent_type', job_config),
        'assistant_overrides': {
            'variable_values': {
                'phone_number': format_phone_for_api(phone_e164),
                'agent_name': resolve_setting('agent_name', job_config),
                'candidate_name': candidate_name,
                'company_name': resolve_setting('company_name', job_config),
                'role': role,
                'datetime_today': datetime_to_words(now),
                'interview_duration': number_to_words(duration_minutes),
                # The call goes out shortly before the slot, so the slot
                # is always the same day -- "today" is safe to hardcode.
                'interview_slot_start': time_to_words(slot_start, 'today'),
                'interview_slot_end': time_to_words(slot_end, 'today'),
                'disqualification_rate': resolve_setting(
                    'disqualification_rate', job_config),
            }
        },
    }


def _add_auth_headers(request):
    """Attach the calling system's auth headers to a request.

    Shared by placing and polling so a rotated key applies to both.
    """
    # The calling system authenticates on this header. Configurable so
    # the key can be rotated in .env without a code change.
    pass_key = _cfg('CALLER_PASS_KEY', 'fabrichqai')
    if pass_key:
        request.add_header('x-pass-key', pass_key)

    api_key = _cfg('CALLER_API_KEY')
    if api_key:
        request.add_header('Authorization', f'Bearer {api_key}')


def place_call(payload, timeout=DEFAULT_TIMEOUT_SECONDS, job_config=None):
    """POST one call request to the calling system.

    Returns (success, error_message, provider_ref). provider_ref is
    whatever id the calling system returns, so a specific call can be
    traced later.
    """
    endpoint = get_call_endpoint(job_config)

    if not payload.get('assistant_id'):
        msg = 'CALLER_ASSISTANT_ID is not set'
        logger.error(msg)
        return False, msg, None

    phone = payload.get('assistant_overrides', {}).get(
        'variable_values', {}).get('phone_number')
    if not phone:
        return False, 'No phone number for this candidate', None

    body = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(
        endpoint, data=body, method='POST',
        headers={'Content-Type': 'application/json'})
    _add_auth_headers(request)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode('utf-8', errors='replace')
            logger.info('Call queued for %s (HTTP %s)', phone, response.status)
            return True, None, _extract_reference(raw)

    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')[:300]
        msg = f'HTTP {exc.code} from calling system: {detail}'
        logger.error('Call failed for %s: %s', phone, msg)
        return False, msg, None
    except urllib.error.URLError as exc:
        msg = f'Cannot reach calling system at {endpoint}: {exc.reason}'
        logger.error(msg)
        return False, msg, None
    except Exception as exc:
        msg = f'Unexpected error calling {endpoint}: {exc}'
        logger.error(msg)
        return False, msg, None


def _extract_reference(raw_response):
    """Pull a call/job id out of the response, if there is one.

    The response shape is owned by the calling system, so this checks
    the usual key names and falls back to a truncated body rather than
    failing when the shape is unfamiliar.
    """
    try:
        data = json.loads(raw_response)
    except (ValueError, TypeError):
        return (raw_response or '').strip()[:120] or None

    if isinstance(data, dict):
        for key in ('call_id', 'id', 'call_sid', 'sid', 'request_id',
                    'job_id', 'reference'):
            if data.get(key):
                return str(data[key])
        # Some APIs nest the id one level down.
        for outer in ('data', 'call', 'result'):
            inner = data.get(outer)
            if isinstance(inner, dict):
                for key in ('call_id', 'id', 'sid'):
                    if inner.get(key):
                        return str(inner[key])
    return json.dumps(data)[:120]


# ==================== POLLING CALL OUTCOMES ====================
#
# Statuses the calling system reports, mapped to the five this
# application stores. Ported from the fabric-recruit LiveKit client so
# both systems classify a call the same way.

STATUS_QUEUED = 'queued'
STATUS_IN_PROGRESS = 'in_progress'
STATUS_COMPLETED = 'completed'
STATUS_FAILED = 'failed'
STATUS_CANCELLED = 'cancelled'

# A call that ended for one of these reasons never reached the
# candidate, so it is not counted as a successful contact.
FAILED_HANGUP_REASONS = {
    'rejected', 'busy', 'voice-mail', 'server-error',
    'llm-error', 'stt-error', 'tts-error', 'unknown',
}

# Below this many seconds a "completed" call did not amount to a real
# conversation -- the candidate hung up as it connected.
MIN_SUCCESSFUL_DURATION_SECONDS = 5


def map_status(raw_status):
    """Normalise the calling system's status to one of ours."""
    if not raw_status:
        return STATUS_QUEUED
    status = str(raw_status).lower()
    if status in ('queued',):
        return STATUS_QUEUED
    if status in ('dialing', 'ringing', 'in_progress'):
        return STATUS_IN_PROGRESS
    if status in ('completed', 'hangup', 'ended', 'finished'):
        return STATUS_COMPLETED
    if status in ('failed', 'error'):
        return STATUS_FAILED
    if status in ('cancelled',):
        return STATUS_CANCELLED
    return status


def is_call_successful(status, hangup_reason, duration):
    """Whether the candidate was actually reached and spoken to."""
    if status != STATUS_COMPLETED:
        return False
    if hangup_reason and str(hangup_reason).lower() in FAILED_HANGUP_REASONS:
        return False
    if 0 < duration < MIN_SUCCESSFUL_DURATION_SECONDS:
        return False
    return True


def _parse_timestamp(value):
    """Parse an ISO-8601 timestamp, tolerating a trailing Z."""
    if not value:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None


def safe_duration(started_at, ended_at):
    """Call length in seconds, or 0 when either timestamp is missing."""
    start = _parse_timestamp(started_at)
    end = _parse_timestamp(ended_at)
    if not start or not end:
        return 0.0
    return max(0.0, (end - start).total_seconds())


def format_transcript(transcript_data):
    """Flatten the transcript into readable 'role: text' lines."""
    if not isinstance(transcript_data, dict):
        return None
    items = transcript_data.get('items')
    if not isinstance(items, list) or not items:
        return None

    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        role = (item.get('role') or '').strip()
        content = item.get('content')
        if not role:
            continue
        if isinstance(content, list):
            text = ' '.join(str(c) for c in content).strip()
        elif isinstance(content, str):
            text = content.strip()
        else:
            continue
        if text:
            lines.append(f'{role}: {text}')

    return ('\n'.join(lines) + '\n') if lines else None


def get_call_details(execution_id, timeout=DEFAULT_TIMEOUT_SECONDS,
                     job_config=None):
    """Fetch the current state of one call.

    Returns a flattened dict. On any failure it returns
    {'success': False, 'error': ...} -- the caller must treat that as
    "unknown, try again", never as a terminal outcome, or a transient
    network blip would silently close out a live call.
    """
    base = resolve_setting('api_base_url', job_config).rstrip('/')
    url = f'{base}/api/v1/call/{execution_id}'

    request = urllib.request.Request(url, method='GET')
    _add_auth_headers(request)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')[:200]
        return {'success': False,
                'error': f'HTTP {exc.code} polling call: {detail}',
                'status_code': exc.code}
    except urllib.error.URLError as exc:
        return {'success': False,
                'error': f'Cannot reach calling system: {exc.reason}'}
    except Exception as exc:
        return {'success': False, 'error': f'Error polling call: {exc}'}

    try:
        body = json.loads(raw)
    except (ValueError, TypeError):
        return {'success': False,
                'error': f'Unparseable response: {raw[:200]}'}

    return flatten_call(body)


def flatten_call(body):
    """Translate the calling system's response into our stored shape."""
    status = map_status(body.get('status'))
    duration = safe_duration(body.get('started_at'), body.get('ended_at'))
    hangup_reason = body.get('ended_reason')
    transcript = format_transcript(body.get('transcript'))
    execution_id = body.get('id')

    # The provider's recording URL expires, so it is never stored or
    # shown directly. The admin page links to our own route, which
    # redirects to a freshly-fetched URL at click time.
    recording_available = bool(body.get('recording_url'))

    return {
        'success': True,
        'execution_id': execution_id,
        'status': status,
        'call_completed': status in (STATUS_COMPLETED, STATUS_FAILED,
                                     STATUS_CANCELLED),
        'call_successful': is_call_successful(status, hangup_reason,
                                              duration),
        'duration': duration,
        'cost': body.get('cost') or 0,
        'transcript': transcript,
        'recording_available': recording_available,
        'hangup_reason': (hangup_reason.lower()
                          if hangup_reason else hangup_reason),
        'answered_by_voice_mail': (
            (hangup_reason or '').lower() == 'voice-mail'),
        'raw': body,
    }


def get_recording_url(execution_id, job_config=None):
    """The calling system's recording endpoint for one call.

    Fetched fresh each time it is needed, since the underlying URL
    expires.
    """
    base = resolve_setting('api_base_url', job_config).rstrip('/')
    return f'{base}/api/v1/call/{execution_id}/recording'
