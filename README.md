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