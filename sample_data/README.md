# Sample Data Files

This directory contains sample CSV files for uploading candidates to the interview slot booking system.

## Files

- `candidates_sde.csv` - Sample candidates for Software Development Engineer I position
- `candidates_data_scientist.csv` - Sample candidates for Data Scientist – I position
- `candidates_business_mgmt.csv` - Sample candidates for Senior Associate – Business Management position

## CSV Format

Each CSV file must contain the following columns:

| Column | Description | Example |
|--------|-------------|---------|
| `name` | Candidate's full name | Rajesh Kumar |
| `email` | Valid email address | rajesh.kumar@example.com |
| `interview_link` | Fabrichq interview link | https://app.fabrichq.ai/jobs/e34e8e92-95ff-47f5-8e2f-86baa397c2a0/?candidate_id=a1b2c3d4... |

## Important: Understanding the Two Different Link Types

### 1. Interview Link (in CSV - what you upload)
**Format:** `https://app.fabrichq.ai/jobs/<JOB_UUID>/?candidate_id=<CANDIDATE_UUID>`

**Example:**
```
https://app.fabrichq.ai/jobs/e34e8e92-95ff-47f5-8e2f-86baa397c2a0/?candidate_id=a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d
```

This is the link from the external Fabrichq system. The app parses this link to extract:
- `job_id` from the URL path
- `candidate_id` from the query parameter

### 2. Slot Booking Link (what candidates receive)
**Format:** `https://slot-booking.fabrichq.ai/book/<job-slug>?c_id=<CANDIDATE_UUID>`

**Examples:**
```
https://slot-booking.fabrichq.ai/book/software-development-engineer-i?c_id=a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d
https://slot-booking.fabrichq.ai/book/data-scientist-i?c_id=f6a7b8c9-d0e1-4f2a-3b4c-5d6e7f8a9b0c
https://slot-booking.fabrichq.ai/book/senior-associate-business-management?c_id=e1f2a3b4-c5d6-4e7f-8a9b-0c1d2e3f4a5b
```

This is the link you send to candidates for booking their interview slots. It uses:
- A human-readable job slug in the URL path
- `c_id` as the query parameter (shortened from `candidate_id`)

## Job Slug Mapping

| Job Name | Job UUID | Job Slug |
|----------|----------|----------|
| Software Development Engineer I | e34e8e92-95ff-47f5-8e2f-86baa397c2a0 | software-development-engineer-i |
| Data Scientist – I | d770069d-de27-4489-bdcc-0122ebf68a05 | data-scientist-i |
| Senior Associate – Business Management | 62566b89-8826-4140-8427-5413e4fa3ec7 | senior-associate-business-management |

## Usage Instructions

1. **Upload the CSV** via the admin panel at `/admin/upload`
2. **Select the job position** that matches the data
3. The system will:
   - Parse the `interview_link` to extract `candidate_id` and `job_id`
   - Validate that the extracted `job_id` matches your selected job
   - Store candidates in the database
4. **Send booking links** to candidates using the new format:
   - Use the job slug (not the UUID)
   - Use `c_id` parameter (not `candidate_id`)

## Example Workflow

1. Admin uploads `candidates_sde.csv` and selects "Software Development Engineer I"
2. System extracts data from interview links and stores candidates
3. Admin sends email to each candidate with their booking link:
   ```
   Dear Rajesh Kumar,

   Please book your interview slot here:
   https://slot-booking.fabrichq.ai/book/software-development-engineer-i?c_id=a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d

   Best regards,
   HR Team
   ```
4. Candidate clicks the link and books their slot

## Validation Rules

- All three columns (name, email, interview_link) are required
- Email must be in valid format
- Interview link must contain a valid job UUID and candidate UUID
- The job UUID in the interview link must match the job you selected during upload
- Candidate UUIDs must be unique per job (same candidate can apply to multiple jobs)
