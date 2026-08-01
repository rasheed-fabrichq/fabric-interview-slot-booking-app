"""
Per-job overrides for the reminder call.

Storage is deliberately isolated behind three functions. Right now the
overrides live in the JOB_CALL_CONFIGS dict below; moving them into the
database later means rewriting only those three bodies, because nothing
outside this module knows where the values come from.

A job with no entry here inherits everything from .env, so the common
case needs no configuration at all. Within an entry, only the keys that
differ need to be set -- anything absent falls back to the env default.

Recognised keys:

    calls_enabled          1 or 0; omit to follow CALLS_ENABLED
    assistant_id           the assistant the calling system should run
    agent_type             e.g. 'integrity_reminder'
    agent_name             the voice agent's name, e.g. 'Riya'
    company_name           the client, e.g. 'Kearney'
    role_name              spoken role; defaults to the job's name
    disqualification_rate  spoken, e.g. 'eighty percent'
    lead_minutes           minutes before the slot to call
    api_base_url           only if this job uses a different service


To move this to the database later
----------------------------------
1. Recreate the job_call_configs table (job_id primary key, one
   nullable column per key above).
2. Replace the three function bodies with the equivalent queries.
3. Delete JOB_CALL_CONFIGS.

No caller changes: get_job_call_config returns a dict of only the keys
a job overrides, get_all_job_call_configs returns those dicts keyed by
job_id, and update_job_call_config persists a partial update.
"""
import copy
import logging

logger = logging.getLogger(__name__)


# Per-job overrides, keyed by job_id. Example of a fully-overridden job:
#
#     '62566b89-8826-4140-8427-5413e4fa3ec7': {
#         'assistant_id': '651dd10a-dac9-4166-8a4c-af7bde973170',
#         'agent_name': 'Meera',
#         'company_name': 'Kearney India',
#         'role_name': 'Data Science Intern',
#         'disqualification_rate': 'sixty percent',
#         'lead_minutes': 45,
#     },
#
JOB_CALL_CONFIGS = {
    # Summer intern - Senior Operations Analyst (Kearney)
    #
    # role_name exists because the agent reads it aloud: the job's own
    # name is "Summer intern - Senior Operations Analyst", and the
    # hyphen does not survive text-to-speech well.
    'ea85d314-1bb4-4bba-8702-d983915c6da6': {
        'agent_name': 'Riya',
        # Spelled "Karney" deliberately: it is read aloud, and this
        # spelling gives the pronunciation the client wants.
        'company_name': 'Karney',
        'role_name': 'Senior Operations Analyst',
    },
}


# Keys a job is allowed to override. Anything else is ignored, so a
# typo cannot silently become part of the payload.
ALLOWED_KEYS = (
    'calls_enabled', 'assistant_id', 'agent_type', 'agent_name',
    'company_name', 'role_name', 'disqualification_rate',
    'lead_minutes', 'api_base_url',
)


def get_job_call_config(job_id):
    """Overrides for one job, or None if it has none.

    Keys set to None are omitted, so the result is only what this job
    actually overrides -- the caller falls back to env for the rest.
    """
    config = JOB_CALL_CONFIGS.get(job_id)
    if not config:
        return None
    return {k: v for k, v in config.items()
            if k in ALLOWED_KEYS and v is not None}


def get_all_job_call_configs():
    """Every job's overrides, keyed by job_id.

    Returns a deep copy: callers must not be able to mutate the
    configuration by editing what they were handed.
    """
    return {
        job_id: {k: v for k, v in config.items() if k in ALLOWED_KEYS}
        for job_id, config in copy.deepcopy(JOB_CALL_CONFIGS).items()
    }


def update_job_call_config(job_id, **fields):
    """Set overrides for a job.

    Pass a key as None to clear it, which restores the env fallback.

    NOTE: while overrides are hardcoded, this only updates the in-memory
    dict -- the change is lost when the process restarts, and a separate
    worker process will not see it at all. It is here so the admin page
    and its tests work against the same interface they will use once
    this is backed by the database.
    """
    updates = {k: v for k, v in fields.items() if k in ALLOWED_KEYS}
    if not updates:
        return {'error': 'No valid fields provided'}

    config = JOB_CALL_CONFIGS.setdefault(job_id, {})
    for key, value in updates.items():
        if value is None:
            config.pop(key, None)
        else:
            config[key] = value

    if not config:
        JOB_CALL_CONFIGS.pop(job_id, None)

    logger.info('Call config updated in memory for job %s: %s',
                job_id, sorted(updates))
    return {'success': True, 'in_memory_only': True}
