# DataClean-Pro

## Cleaning history database update

Cleaning history is stored in the `cleaning_history` table. Apply the schema from
PowerShell at the repository root after configuring MySQL:

```powershell
Get-Content .\backend\database\schema.sql | mysql -u YOUR_DB_USER -p
```

The schema uses `CREATE TABLE IF NOT EXISTS`; running it against the existing
`datacleanpro` database does not drop tables or reset data. The schema currently
selects `datacleanpro` explicitly, so make sure that matches `DB_NAME` in
`backend\.env` before applying it. MySQL prompts for the database user's password.

## Persistent cleaned CSV downloads

The `/api/clean` feature requires the `cleaned_file_id` column and its unique
index on `cleaning_history`. For an existing database, apply the idempotent
migration against the same database configured by `DB_NAME`:

```powershell
Get-Content .\backend\database\migrations\20261024_add_cleaned_file_id.sql | mysql -u YOUR_DB_USER -p datacleanpro
```

The migration adds a nullable reference and unique index without altering or
deleting existing history records. Existing records remain visible but have no
persisted cleaned file to download. New cleaned CSV output is stored privately
under `backend\private\cleaned_exports`; that directory is excluded from Git.
Keep it on persistent server storage and restrict filesystem access to the
backend service account. No uploaded original CSV is retained.

## Verification

Run the backend unit tests and Python syntax check from PowerShell:

```powershell
Set-Location .\backend
.\venv\Scripts\python.exe -m unittest discover -s .\tests -v
.\venv\Scripts\python.exe -m compileall routes tests
```

Build the frontend:

```powershell
Set-Location ..\frontend
npm.cmd run build
```