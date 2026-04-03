# Vertica Database Navigator

A lightweight Python web application for browsing a Vertica database structure and running SQL queries from a web browser.

This repository is centered around the script `19_vertica_navigator.py`, which starts a local HTTP server, connects to Vertica, displays schemas/tables/views in a tree, and lets the user execute SQL queries from the browser. The script reads credentials from a local JSON file and serves a logo image from the `ASSETS` folder. Based on the code, the application uses port `8001`, expects a credentials file at `ASSETS/vertica_credentials.json`, and serves the logo from `ASSETS/verticalogo.png`.[^code]

---

## Disclaimer

This code is provided **as is**, with **no warranty of any kind**, express or implied. The user runs and uses this code **entirely at their own responsibility and risk**.

A valid **Vertica license is required** in order to use Vertica. The Vertica license is **not included** with this project and must be **purchased separately** from Vertica.

---

## What this project does

The application provides:

- a browser-based database tree
- display of schemas, tables, columns, views, and system tables
- SQL query editing
- execution of SQL statements from the browser
- simple SQL beautification
- result tabs for multiple queries
- local logging to `vertica_navigator.log`

---

## Repository layout

Your GitHub repository should look like this:

```text
.
├── 19_vertica_navigator.py
├── README.md
├── LICENSE
├── .gitignore
└── ASSETS/
    ├── verticalogo.png
    └── vertica_credentials.json
```

## Important asset location

The logo file location must be **exactly**:

```text
ASSETS/verticalogo.png
```

Do not place it in another folder and do not rename it, because the application expects this exact path.

---

## Requirements

### Operating system

Tested in a Linux environment such as Ubuntu.

### Python

Use Python 3.

### Python packages and system package

The script itself includes setup notes that indicate the following installation steps:[^code]

```bash
sudo apt install python3-pip
pip install verticapy
pip install vertica-python
sudo apt install unixodbc-dev
pip install pyodbc
```

---

## Credentials file

The application reads database credentials from:

```text
ASSETS/vertica_credentials.json
```

We did not provide a real credentials file.
Instead, you need to edit and update the following file:

```text
ASSETS/vertica_credentials.json
```

### Sample credentials file

```json
{
  "host": "127.0.0.1",
  "port": 5433,
  "user": "dbadmin",
  "password": "YOUR_PASSWORD_HERE",
  "database": "YOUR_DATABASE_NAME_HERE",
  "read_timeout": 600
}
```

### Important note about `host`

The value:

```json
"host": "127.0.0.1"
```

is **only an example**.

Your Vertica server may be running on a different machine or network address, so the host can be a real IP address or hostname.

For security reasons, the real server address is not written in the public sample file. The user must set the correct value according to their own environment.

---

## How to prepare the real credentials file

1. Copy the sample file:

```bash
cp vertica_credentials.json ASSETS/vertica_credentials.json
```

2. Edit `ASSETS/vertica_credentials.json` and replace the placeholder values with the real Vertica connection details.

3. Keep `ASSETS/vertica_credentials.json` private and local.

---

## How to run

Run the script as the relevant user, for example:

```bash
python3 19_vertica_navigator.py
```

The script starts a local web server on port `8001`.[^code]

---

## How to open the application in the browser

After the server starts, open a browser (like Chrom) and go to the machine IP address with port `8001`.

Example:

```text
http://10.10.10.3:8001
```

### How to find the machine IP address

Run:

```bash
hostname -I
```

Use the relevant returned IP address in the browser.

### Browser note

Tested with **Chrome**.

---

## Application behavior summary

From the attached script, the application:

- serves the main page at `/`
- loads the database tree from `/api/dbtree`
- executes SQL through `/api/execute_query`
- beautifies SQL through `/api/beautify_sql`
- serves static assets from `/ASSETS/...`[^code]

---

## Security notes

- Never commit real database credentials.
- Keep `ASSETS/vertica_credentials.json` out of GitHub.
- Publish only the sample credentials file.
- Review access controls before exposing the server to any network.
- This application starts a Python-based web server that communicates with the browser over HTTP. The connection is not encrypted. Do not use it over untrusted networks. For safer use, run it only on localhost or within a trusted private network environment.
- This tool can execute SQL statements, so use it carefully and only in environments where you accept that risk.

---

