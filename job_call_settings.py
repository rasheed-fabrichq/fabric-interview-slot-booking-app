"""
Per-job overrides for the reminder call.

Stored in the call_* columns of job_configs and edited from the admin
Communications page. Nothing outside this module knows the column
names: callers get a dict keyed by the names below.

A job with no value for a key inherits it from .env, so the common
case needs no configuration at all.

Recognised keys:

    calls_enabled          1 or 0; absent to follow CALLS_ENABLED
    assistant_id           the assistant the calling system should run
    agent_type             e.g. 'integrity_reminder'
    agent_name             the voice agent's name, e.g. 'Riya'
    company_name           the client as spoken; defaults to the job's
                           company name
    role_name              spoken role; defaults to the job's name
    disqualification_rate  spoken, e.g. 'eighty percent'
    lead_minutes           minutes before the slot to call
    api_base_url           only if this job uses a different service
"""
import logging

from database import (
    get_job_communication, get_all_job_communications,
    update_job_communication,
)

logger = logging.getLogger(__name__)


# Maps each call setting to its job_configs column.
COLUMNS = {
    'calls_enabled': 'call_enabled',
    'assistant_id': 'call_assistant_id',
    'agent_type': 'call_agent_type',
    'agent_name': 'call_agent_name',
    'company_name': 'call_company_name',
    'role_name': 'call_role_name',
    'disqualification_rate': 'call_disqualification_rate',
    'lead_minutes': 'call_lead_minutes',
    'api_base_url': 'call_api_base_url',
}

ALLOWED_KEYS = tuple(COLUMNS)


def _to_call_config(row):
    """A job_configs row as call overrides, omitting unset values.

    The spoken company falls back to the job's company name before the
    env default: a job set up for a client should not have its agent
    name a different company just because the call field was left blank.
    """
    config = {key: row[column] for key, column in COLUMNS.items()
              if row.get(column) not in (None, '')}
    if 'company_name' not in config and row.get('company_name'):
        config['company_name'] = row['company_name']
    return config


def get_job_call_config(job_id):
    """Overrides for one job, or None if it has none."""
    row = get_job_communication(job_id)
    if not row:
        return None
    return _to_call_config(row) or None


def get_all_job_call_configs():
    """Every job's overrides, keyed by job_id. Jobs with none are omitted."""
    configs = {}
    for job_id, row in get_all_job_communications().items():
        config = _to_call_config(row)
        if config:
            configs[job_id] = config
    return configs


def update_job_call_config(job_id, **fields):
    """Set overrides for a job. Pass a key as None to restore the env value."""
    updates = {COLUMNS[k]: v for k, v in fields.items() if k in COLUMNS}
    if not updates:
        return {'error': 'No valid fields provided'}

    result = update_job_communication(job_id, **updates)
    if 'success' in result:
        logger.info('Call config updated for job %s: %s',
                    job_id, sorted(fields))
    return result
