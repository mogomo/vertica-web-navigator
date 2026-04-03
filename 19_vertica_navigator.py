# =============================================================================
# File name: 19_vertica_navigator.py
# Usage: As user dbadmin do:  python3 19_vertica_navigator.py
# Before running this script (on Ubuntu) do:
# sudo apt install python3-pip
# pip install verticapy
# pip install vertica-python
# sudo apt install unixodbc-dev
# pip install pyodbc
#
# =============================================================================
# SECTION 0: IMPORTS AND INITIALIZATION
# Purpose: Import required libraries and set up logging
# Modification Note: Add new imports here when extending functionality
# =============================================================================


DEBUG_LOGGING = True

import vertica_python
import http.server
import socketserver
from urllib.parse import urlparse, parse_qs
import json
import os
import logging
from typing import Dict, List
import time

# Configure logging based on DEBUG_LOGGING flag
if DEBUG_LOGGING:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
        handlers=[
            logging.FileHandler('vertica_navigator.log'),
            logging.StreamHandler()
        ]
    )
else:
    logging.basicConfig(
        level=logging.ERROR,
        format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
        handlers=[logging.StreamHandler()]
    )

logger = logging.getLogger('VerticaNavigator')

def log_info(message):
    if DEBUG_LOGGING:
        logger.info(message)

def read_credentials():
    log_info("Reading credentials file...")
    try:
        credentials_path = os.path.join(os.path.dirname(__file__), 'ASSETS', 'vertica_credentials.json')
        with open(credentials_path, 'r', encoding='utf-8') as f:
            creds = json.load(f)
            log_info("Credentials loaded successfully")
            return creds
    except Exception as e:
        logger.error(f"Failed to read credentials: {str(e)}")
        raise



def split_sql_statements(sql_text):
    statements = []
    current = []
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    i = 0
    length = len(sql_text)

    while i < length:
        ch = sql_text[i]
        nxt = sql_text[i + 1] if i + 1 < length else ''

        if in_line_comment:
            current.append(ch)
            if ch in ('\n', '\r'):
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            current.append(ch)
            if ch == '*' and nxt == '/':
                current.append(nxt)
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue

        if in_single:
            current.append(ch)
            if ch == "'":
                if nxt == "'":
                    current.append(nxt)
                    i += 2
                    continue
                in_single = False
            i += 1
            continue

        if in_double:
            current.append(ch)
            if ch == '"':
                if nxt == '"':
                    current.append(nxt)
                    i += 2
                    continue
                in_double = False
            i += 1
            continue

        if ch == '-' and nxt == '-':
            current.append(ch)
            current.append(nxt)
            in_line_comment = True
            i += 2
            continue

        if ch == '/' and nxt == '*':
            current.append(ch)
            current.append(nxt)
            in_block_comment = True
            i += 2
            continue

        if ch == "'":
            current.append(ch)
            in_single = True
            i += 1
            continue

        if ch == '"':
            current.append(ch)
            in_double = True
            i += 1
            continue

        if ch == ';':
            statement = ''.join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    tail = ''.join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def beautify_single_statement(sql):
    sql = sql.strip()
    if not sql:
        return ''

    clause_keywords = [
        'SELECT', 'FROM', 'WHERE', 'GROUP BY', 'HAVING', 'ORDER BY',
        'INNER JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'FULL JOIN', 'CROSS JOIN', 'JOIN',
        'UNION', 'INTERSECT', 'EXCEPT', 'WITH', 'UPDATE', 'DELETE',
        'INSERT INTO', 'VALUES', 'SET', 'LIMIT', 'OFFSET', 'ON'
    ]
    logical_keywords = {'AND', 'OR'}
    uppercase_keywords = {
        'SELECT', 'FROM', 'WHERE', 'GROUP', 'BY', 'HAVING', 'ORDER', 'INNER', 'LEFT',
        'RIGHT', 'FULL', 'CROSS', 'JOIN', 'UNION', 'INTERSECT', 'EXCEPT', 'WITH',
        'UPDATE', 'DELETE', 'INSERT', 'INTO', 'VALUES', 'SET', 'LIMIT', 'OFFSET',
        'ON', 'AND', 'OR', 'AS', 'DISTINCT', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END',
        'IN', 'IS', 'NOT', 'NULL', 'LIKE', 'BETWEEN', 'EXISTS'
    }
    indent_unit = '    '

    tokens = []
    i = 0
    length = len(sql)

    def is_word_char(ch):
        return ch.isalnum() or ch == '_' or ch == '$'

    while i < length:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < length else ''

        if ch.isspace():
            i += 1
            continue

        if ch == '-' and nxt == '-':
            start = i
            i += 2
            while i < length and sql[i] not in ('\n', '\r'):
                i += 1
            tokens.append(('comment', sql[start:i]))
            continue

        if ch == '/' and nxt == '*':
            start = i
            i += 2
            while i < length - 1:
                if sql[i] == '*' and sql[i + 1] == '/':
                    i += 2
                    break
                i += 1
            tokens.append(('comment', sql[start:i]))
            continue

        if ch == "'":
            start = i
            i += 1
            while i < length:
                if sql[i] == "'":
                    i += 1
                    if i < length and sql[i] == "'":
                        i += 1
                        continue
                    break
                i += 1
            tokens.append(('string', sql[start:i]))
            continue

        if ch == '"':
            start = i
            i += 1
            while i < length:
                if sql[i] == '"':
                    i += 1
                    if i < length and sql[i] == '"':
                        i += 1
                        continue
                    break
                i += 1
            tokens.append(('identifier', sql[start:i]))
            continue

        if is_word_char(ch):
            start = i
            i += 1
            while i < length and is_word_char(sql[i]):
                i += 1
            value = sql[start:i]
            upper = value.upper()
            if upper in uppercase_keywords:
                value = upper
            tokens.append(('word', value))
            continue

        if ch in ('<', '>', '!', '|', ':') and nxt:
            two = ch + nxt
            if two in ('<=', '>=', '<>', '!=', '||', '::'):
                tokens.append(('symbol', two))
                i += 2
                continue

        tokens.append(('symbol', ch))
        i += 1

    merged = []
    i = 0
    while i < len(tokens):
        tok_type, tok_value = tokens[i]
        if tok_type == 'word' and i + 1 < len(tokens) and tokens[i + 1][0] == 'word':
            pair = tok_value + ' ' + tokens[i + 1][1]
            if pair in clause_keywords:
                merged.append(('clause', pair))
                i += 2
                continue
        if tok_type == 'word' and tok_value in clause_keywords:
            merged.append(('clause', tok_value))
        else:
            merged.append((tok_type, tok_value))
        i += 1

    lines = []
    current = ''
    indent = 0
    in_select_list = False
    in_set_list = False
    paren_stack = []

    def flush():
        nonlocal current
        line = current.rstrip()
        if line:
            lines.append(line)
        current = ''

    def ensure_indent(extra=0):
        nonlocal current
        if not current:
            current = indent_unit * max(indent + extra, 0)

    def append_token(value, spaced=True):
        nonlocal current
        ensure_indent()
        if not current.strip():
            current += value
        elif not spaced or current.endswith('(') or current.endswith('.'):
            current += value
        else:
            current += ' ' + value

    for index, token in enumerate(merged):
        tok_type, tok_value = token
        next_token = merged[index + 1] if index + 1 < len(merged) else None

        if tok_type == 'comment':
            flush()
            lines.append((indent_unit * indent) + tok_value)
            continue

        if tok_type == 'clause':
            flush()
            current = (indent_unit * indent) + tok_value
            in_select_list = (tok_value == 'SELECT')
            in_set_list = (tok_value == 'SET')
            if tok_value in ('FROM', 'WHERE', 'GROUP BY', 'HAVING', 'ORDER BY', 'LIMIT', 'OFFSET', 'VALUES'):
                in_select_list = False
            continue

        if tok_type == 'word' and tok_value in logical_keywords:
            flush()
            current = (indent_unit * (indent + 1)) + tok_value
            continue

        if tok_type in ('string', 'identifier', 'word'):
            append_token(tok_value)
            continue

        if tok_type == 'symbol':
            if tok_value == '.':
                ensure_indent()
                current = current.rstrip() + '.'
            elif tok_value == ',':
                ensure_indent()
                current += ','
                if in_select_list or in_set_list:
                    flush()
            elif tok_value == '(':
                previous = merged[index - 1] if index > 0 else None
                is_function = previous and previous[0] in ('word', 'identifier')
                is_subquery = next_token and next_token[0] == 'clause' and next_token[1] in ('SELECT', 'WITH')
                ensure_indent()
                current = current.rstrip() + '('
                paren_stack.append((is_function, is_subquery))
                if is_subquery:
                    flush()
                    indent += 1
            elif tok_value == ')':
                is_function = False
                is_subquery = False
                if paren_stack:
                    is_function, is_subquery = paren_stack.pop()
                if is_subquery:
                    flush()
                    indent = max(indent - 1, 0)
                    current = (indent_unit * indent) + ')'
                else:
                    ensure_indent()
                    current = current.rstrip() + ')'
            else:
                append_token(tok_value)

    flush()
    return '\n'.join(lines)


def beautify_sql_text(sql_text):
    statements = split_sql_statements(sql_text)
    formatted = []
    for statement in statements:
        beautified = beautify_single_statement(statement)
        if beautified:
            formatted.append(beautified)
    if not formatted:
        return ''
    return ';\n\n'.join(formatted) + ';'

# Section 1: Backend Query Execution Handler - v1.0
# Goal: Add new endpoint for query execution while maintaining existing endpoints

class DBTreeHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        if DEBUG_LOGGING:
            logger.info(format%args)

    def do_GET(self):
        try:
            if self.path == '/':
                log_info("Serving homepage")
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(homepage_html.encode('utf-8'))
            elif self.path == '/api/dbtree':
                log_info("Processing database tree request")
                self.get_tree()
            elif self.path.startswith('/ASSETS/'):
                log_info(f"Serving asset: {self.path}")
                return http.server.SimpleHTTPRequestHandler.do_GET(self)
        except Exception as e:
            logger.error(f"Error handling GET request: {str(e)}")
            self.send_error(500, str(e))

    # [Section 1: Backend Tree Structure Update - v1.4]
# Changes:
# - Simplified tree hierarchy
# - Maintained all existing functionality
# - Updated root node structure

    def get_tree(self):
        start_time = time.time()
        try:
            log_info("Establishing database connection...")
            conn_info = read_credentials()
            with vertica_python.connect(**conn_info) as connection:
                log_info("Database connection established")
                with connection.cursor() as cursor:
                    # Get database name
                    cursor.execute("SELECT database_name FROM databases")
                    db_name = cursor.fetchone()[0]
                    log_info(f"Database name retrieved: {db_name}")

                    # Get system tables
                    log_info("Fetching system tables...")
                    cursor.execute("""
                        SELECT table_name, remarks
                        FROM all_tables
                        WHERE table_type = 'SYSTEM TABLE'
                        ORDER BY table_name
                    """)
                    system_tables = cursor.fetchall()
                    log_info(f"Retrieved {len(system_tables)} system tables")

                    # Get all schemas, including empty schemas with no tables or views
                    log_info("Fetching schemas...")
                    cursor.execute("""
                        SELECT schema_name
                        FROM schemata
                        ORDER BY schema_name
                    """)
                    schema_rows = cursor.fetchall()
                    log_info(f"Retrieved {len(schema_rows)} schemas")

                    # Get tables and columns (existing code)
                    cursor.execute("""
                        SELECT table_namespace, table_schema, table_name, column_name, data_type
                        FROM columns
                        ORDER BY 1,2,3,4,ordinal_position
                    """)
                    table_rows = cursor.fetchall()
                    log_info(f"Retrieved {len(table_rows)} rows of table data")

                    # Get views information (existing code)
                    cursor.execute("""
                        SELECT table_id as view_id_join_key,
                               table_namespace as view_table_namespace,
                               table_schema as view_schema,
                               table_name as view_name,
                               view_definition
                        FROM VIEWS
                    """)
                    view_rows = cursor.fetchall()
                    log_info(f"Retrieved {len(view_rows)} rows of view data")

                    # Build simplified tree structure
                    root = {
                        "name": f"Database {db_name}",
                        "type": "root",
                        "children": [
                            {
                                "name": "Schemas",
                                "type": "category",
                                "children": []
                            },
                            {
                                "name": "System Tables",
                                "type": "category",
                                "children": []
                            }
                        ]
                    }

                    # Add system tables to tree with remarks as children
                    system_tables_node = root["children"][1]
                    for table_name, remarks in system_tables:
                        system_table_node = {
                            "name": table_name,
                            "type": "system_table",
                            "isCheckable": True,
                            "children": []
                        }

                        # Add remarks as a child node if they exist
                        if remarks:
                            system_table_node["children"].append({
                                "name": f" - {remarks}",
                                "type": "system_table_remarks",
                                "children": []
                            })

                        system_tables_node["children"].append(system_table_node)

                    # Process regular schemas
                    schemas_list = root["children"][0]["children"]
                    schema_dict = {}

                    # Seed schema_dict with every schema so empty schemas also appear in the tree,
                    # except the internal/system schemas that should be hidden from the Schemas group.
                    excluded_schemas = {
                        "v_catalog",
                        "v_func",
                        "v_internal",
                        "v_internal_tables",
                        "v_monitor",
                        "v_secret_managers",
                        "v_txtindex",
                    }

                    for schema_row in schema_rows:
                        schema_name = schema_row[0]
                        if schema_name in excluded_schemas:
                            continue
                        schema_dict[schema_name] = {
                            "name": schema_name,
                            "type": "schema",
                            "tables": {},
                            "views": {},
                            "children": [
                                {
                                    "name": "Tables",
                                    "type": "category",
                                    "children": []
                                },
                                {
                                    "name": "Views",
                                    "type": "category",
                                    "children": []
                                }
                            ]
                        }

                    # [Rest of the existing schema/table/view processing code remains unchanged...]

                    # Process tables by schema
                    for row in table_rows:
                        namespace, schema, table, column, data_type = row

                        if schema not in schema_dict:
                            schema_dict[schema] = {
                                "name": schema,
                                "type": "schema",
                                "tables": {},
                                "views": {},
                                "children": [
                                    {
                                        "name": "Tables",
                                        "type": "category",
                                        "children": []
                                    },
                                    {
                                        "name": "Views",
                                        "type": "category",
                                        "children": []
                                    }
                                ]
                            }

                        tables_dict = schema_dict[schema]["tables"]
                        if table not in tables_dict:
                            tables_dict[table] = {
                                "name": table,
                                "type": "table",
                                "isCheckable": True,
                                "children": [{
                                    "name": "Columns",
                                    "type": "category",
                                    "children": []
                                }]
                            }

                        tables_dict[table]["children"][0]["children"].append({
                            "name": f"{column} - {data_type}",
                            "type": "column"
                        })

                    # Process views (existing code remains unchanged)
                    for row in view_rows:
                        view_id, namespace, schema, view_name, view_def = row

                        if schema not in schema_dict:
                            continue

                        schema_dict[schema]["views"][view_name] = {
                            "name": view_name,
                            "type": "view",
                            "isCheckable": True,
                            "children": [{
                                "name": view_def,
                                "type": "view_definition"
                            }]
                        }

                    # Organize final tree structure
                    for schema_name in sorted(schema_dict.keys()):
                        schema_data = schema_dict[schema_name]
                        schema_node = {
                            "name": schema_name,
                            "type": "schema",
                            "children": [
                                {
                                    "name": "Tables",
                                    "type": "category",
                                    "children": []
                                },
                                {
                                    "name": "Views",
                                    "type": "category",
                                    "children": []
                                }
                            ]
                        }

                        # Add tables
                        for table_name in sorted(schema_data["tables"].keys()):
                            schema_node["children"][0]["children"].append(
                                schema_data["tables"][table_name]
                            )

                        # Add views
                        for view_name in sorted(schema_data["views"].keys()):
                            schema_node["children"][1]["children"].append(
                                schema_data["views"][view_name]
                            )

                        schemas_list.append(schema_node)

                    log_info("Tree structure created successfully")

                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(root).encode('utf-8'))

                    if DEBUG_LOGGING:
                        end_time = time.time()
                        log_info(f"Tree generation completed in {end_time - start_time:.2f} seconds")

        except Exception as e:
            logger.error(f"Error getting DB structure: {str(e)}")
            self.send_error(500, str(e))

    def do_POST(self):
        try:
            if self.path == '/api/execute_query':
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                query_data = json.loads(post_data.decode('utf-8'))

                log_info(f"Executing query: {query_data['query']}")

                try:
                    conn_info = read_credentials()
                    with vertica_python.connect(**conn_info) as connection:
                        with connection.cursor() as cursor:
                            cursor.execute(query_data['query'])

                            # cursor.description is None for statements that do not
                            # return a result set, such as CREATE / INSERT / UPDATE / DELETE.
                            if cursor.description:
                                columns = [desc[0] for desc in cursor.description]
                                rows = cursor.fetchall()
                                row_count = len(rows)
                            else:
                                columns = ['status', 'message', 'rows_affected']
                                affected_rows = cursor.rowcount if cursor.rowcount is not None and cursor.rowcount >= 0 else 0
                                rows = [[
                                    'success',
                                    'Statement executed successfully.',
                                    affected_rows
                                ]]
                                row_count = affected_rows

                            # Ensure DDL / DML statements are persisted.
                            connection.commit()

                            result = {
                                'columns': columns,
                                'rows': rows,
                                'rowCount': row_count,
                                'hasResultSet': bool(cursor.description)
                            }

                            self.send_response(200)
                            self.send_header('Content-type', 'application/json')
                            self.end_headers()
                            self.wfile.write(json.dumps(result, default=str).encode('utf-8'))

                except Exception as e:
                    logger.error(f"Query execution error: {str(e)}")
                    self.send_error(500, str(e))

            elif self.path == '/api/beautify_sql':
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                query_data = json.loads(post_data.decode('utf-8'))
                sql_text = query_data.get('query', '')
                result = {'query': beautify_sql_text(sql_text)}
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode('utf-8'))

        except Exception as e:
            logger.error(f"Error handling POST request: {str(e)}")
            self.send_error(500, str(e))

# Section 2: Frontend Query Interface - v1.0
# Query editor and results area while maintaining tree view functionality

homepage_html = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Vertica Database Navigator</title>
    <link rel="icon" type="image/x-icon" href="/ASSETS/verticalogo.png">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
            margin: 0;
            padding: 0;
            font-size: 12px;
            height: 100vh;
            overflow: hidden;
        }
        .main-container {
            display: flex;
            height: 100vh;
            position: relative;
            overflow: hidden;
        }
        .tree-wrapper {
            position: relative;
            flex-shrink: 0;
            display: flex;
            height: 100vh;
        }
        .tree-panel {
            width: 350px;
            min-width: 200px;
            max-width: 800px;
            background-color: white;
            border-right: 1px solid #ddd;
            display: flex;
            flex-direction: column;
            height: 100vh;
        }
        .tree-toolbar {
            display: flex;
            flex-direction: column;
            gap: 8px;
            padding: 8px;
            border-bottom: 1px solid #ddd;
            background: #fafafa;
        }
        .tree-filter-row {
            display: flex;
            gap: 8px;
            align-items: center;
        }
        .tree-filter-input {
            flex: 1;
            min-width: 0;
            padding: 6px 8px;
            border: 1px solid #ccc;
            border-radius: 4px;
            font-size: 12px;
            box-sizing: border-box;
        }
        .tree-action-button {
            padding: 6px 12px;
            background-color: #0066cc;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            white-space: nowrap;
        }
        .tree-action-button:hover {
            background-color: #0052a3;
        }
        .tree-container {
            flex: 1;
            padding: 8px;
            overflow-y: auto;
            overflow-x: hidden;
            min-height: 0;
        }
        .resizer {
            width: 5px;
            background: #f0f0f0;
            cursor: col-resize;
            height: 100vh;
            position: absolute;
            right: 0;
            top: 0;
            transition: background-color 0.3s;
            z-index: 1;
        }
        .vertical-resizer {
            width: 100%;
            height: 5px;
            background: #f0f0f0;
            cursor: row-resize;
            transition: background-color 0.3s;
            margin: 3px 0;
        }
        .resizer:hover, .resizer.dragging,
        .vertical-resizer:hover, .vertical-resizer.dragging {
            background: #0066cc;
        }
        .tree-node {
            padding: 2px 0;
            cursor: pointer;
            display: block;
        }
        .tree-node:hover {
            background-color: #e8e8e8;
        }
        .children {
            margin-left: 20px;
            display: none;
            border-left: 1px dotted #ccc;
            padding-left: 8px;
        }
        .expanded > .children {
            display: block;
        }
        .node-content {
            display: flex;
            align-items: center;
        }
        .icon {
            width: 16px;
            height: 16px;
            margin-right: 4px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }
        .checkbox {
            margin-right: 4px;
            cursor: pointer;
        }
        .name {
            color: #333;
            white-space: pre-wrap;
            word-break: break-word;
            max-width: 100%;
            overflow-wrap: break-word;
        }
        .category { color: #666; font-weight: 500; }
        .database { color: #0066cc; font-weight: 500; }
        .content-area {
            flex: 1;
            display: flex;
            flex-direction: column;
            background-color: #f5f5f5;
            min-width: 200px;
            overflow: hidden;
            padding: 16px;
            gap: 16px;
            box-sizing: border-box;
        }
        .content-wrapper {
            display: flex;
            flex-direction: column;
            gap: 8px;
            height: calc(100vh - 80px); /* Optimized from 95px to maximize space */
            width: calc(100% - 32px);
            overflow: hidden;
        }
        .results-section {
            width: 100%;
            height: 50%;
            min-height: 100px;
            display: flex;           /* Added */
            flex-direction: column;  /* Added */
            border: 1px solid #ddd;
            background: white;
            box-sizing: border-box;
        }
        .content-footer {
            padding: 1px 0;
            font-size: 9px;
            color: #666;
            line-height: 1;
            text-align: center;
            border-top: 1px solid #eee;
            margin-top: auto;    /* Pushes footer to bottom */
            flex-shrink: 0;      /* Prevents shrinking */
        }
        .disclaimer-text {
            color: #666;
            font-size: 9px;   /* Slightly smaller but still readable */
            display: block;
            text-align: center;
            line-height: 1;   /* Minimum line height */
        }
        .view { color: #6b4c9a; }
        .view_definition {
            color: #666;
            font-family: monospace;
            font-size: 11px;
            white-space: pre-wrap;
            padding: 4px;
            background: #f8f8f8;
            border: 1px solid #eee;
            margin-top: 4px;
        }
        .table_category, .view_category { color: #666; font-weight: normal; }
        .system_table_remarks {
            color: #666;
            font-style: italic;
            padding-left: 20px;
            cursor: default;
        }
        .user-select-none {
            user-select: none;
            -webkit-user-select: none;
            -moz-user-select: none;
            -ms-user-select: none;
        }
        .query-section {
            width: 100%;
            height: 50%;
            min-height: 100px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .query-editor {
            width: 100%;
            height: calc(100% - 40px);
            font-family: monospace;
            font-size: 12px;
            padding: 8px;
            resize: none;
            border: 1px solid #ddd;
            background: white;
            overflow: auto;
            box-sizing: border-box;
        }
        .button-container {
            display: flex;
            gap: 8px;
        }
        .query-button {
            padding: 6px 12px;
            background-color: #0066cc;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }
        .query-button:hover {
            background-color: #0052a3;
        }
        .sql-keyword {
            color: #0066cc;
            font-weight: bold;
        }
        .results-section {
            width: 100%;
            height: 50%;
            min-height: 100px;
            overflow: hidden;
            border: 1px solid #ddd;
            background: white;
            box-sizing: border-box;
        }
        .results-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
        }
        .results-table th,
        .results-table td {
            border: 1px solid #ddd;
            padding: 6px 8px;
            text-align: left;
        }
        .results-table th {
            background-color: #f5f5f5;
            font-weight: 500;
        }

        /* New tab-related styles */
        .tab-container {
            display: flex;
            flex-direction: column;
            height: 100%;
            background: white;
        }
        .tab-header {
            display: flex;
            background: #f5f5f5;
            border-bottom: 1px solid #ddd;
            overflow-x: auto;
            min-height: 32px;
        }
        .tab {
            padding: 8px 16px;
            background: white;
            border: 1px solid #ddd;
            border-bottom: none;
            margin: 4px 4px 0 0;
            border-radius: 4px 4px 0 0;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
        }
        .tab.active {
            background: #444444;
            color: white;
            border-color: #333333;
        }
        .tab-close {
            width: 16px;
            height: 16px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(0,0,0,0.1);
            cursor: pointer;
        }
        .tab-content {
            flex: 1;
            overflow: auto;
            padding: 8px;
            display: none;
        }
        .tab-content.active {
            display: block;
        }
        .execution-info {
            font-size: 11px;
            color: #666;
            margin-bottom: 8px;
        }
        .error-tab {
            color: #dc3545;
            background: #fff5f5;
        }
        .loading-indicator {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid #f3f3f3;
            border-top: 2px solid #0066cc;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="main-container">
        <div class="tree-wrapper">
            <div id="treePanel" class="tree-panel">
                <div class="tree-toolbar">
                    <button class="tree-action-button" onclick="refreshTree()">Refresh</button>
                    <div class="tree-filter-row">
                        <input id="treeFilterInput" class="tree-filter-input" type="text" placeholder="Filter schemas or tables..." onkeydown="handleFilterKey(event)">
                        <button class="tree-action-button" onclick="applyTreeFilter()">Filter</button>
                    </div>
                </div>
                <div id="tree" class="tree-container"></div>
            </div>
            <div class="resizer" id="dragMe"></div>
        </div>
        <div class="content-area">
            <div style="display: flex; justify-content: space-between; align-items: center; margin: 0;">
                <h1 style="margin: 0; font-size: 18px; color: #0066cc;">Database Navigator</h1>
            </div>
            <div class="content-wrapper">
                <div class="query-section">
                    <textarea id="queryEditor" class="query-editor" placeholder="Write your SQL queries here... Separate multiple queries with semicolons (;)"></textarea>
                    <div class="button-container">
                        <button class="query-button" onclick="generateQuery()">Generate Query</button>
                        <button class="query-button" onclick="beautifySQL()">
                            <span>✨</span> Beautify
                        </button>
                        <button class="query-button" onclick="executeQueries()">Run Queries</button>
                        <button class="query-button" onclick="clearAll()">Clear All</button>
                    </div>
                </div>
                <div class="vertical-resizer" id="verticalDragMe"></div>
                <div class="results-section">
                   <div class="tab-container">
                       <div id="tabHeader" class="tab-header"></div>
                       <div id="tabContent" class="tab-container"></div>
                   </div>
                   <div class="content-footer">This program is provided 'as is' without warranty of any kind. Users assume all risks associated with its use. No rights to the program are granted. A valid Vertica product license is required for Vertica usage. Created by Maya Goldberg.
                   </div>
                </div>
            </div>
        </div>
    </div>
    <script>
        // Tree loading and manipulation
        let fullTreeData = null;
        let currentTreeData = null;

        async function loadTree() {
            try {
                const response = await fetch('/api/dbtree');
                if (!response.ok) throw new Error('Failed to load tree data');
                const data = await response.json();
                fullTreeData = data;
                currentTreeData = data;
                renderTree(data);
            } catch (error) {
                console.error('Error loading tree:', error);
                document.getElementById('tree').innerHTML =
                    '<div style="color: red; padding: 10px;">Error loading database structure</div>';
            }
        }

        function renderTree(data) {
            document.getElementById('tree').innerHTML = renderNode(data);
        }

        async function refreshTree() {
            const filterInput = document.getElementById('treeFilterInput');
            if (filterInput) {
                filterInput.value = '';
            }
            await loadTree();
        }

        function handleFilterKey(event) {
            if (event.key === 'Enter') {
                applyTreeFilter();
            }
        }

        function applyTreeFilter() {
            if (!fullTreeData) {
                return;
            }

            const filterValue = document.getElementById('treeFilterInput').value.trim().toLowerCase();
            if (!filterValue) {
                currentTreeData = fullTreeData;
                renderTree(currentTreeData);
                return;
            }

            const filteredTree = filterTreeData(fullTreeData, filterValue);
            currentTreeData = filteredTree;
            renderTree(filteredTree);

            document.querySelectorAll('.tree-node').forEach(node => {
                if (node.querySelector('.children')) {
                    node.classList.add('expanded');
                }
            });
        }

        function filterTreeData(treeData, filterValue) {
            const clonedRoot = JSON.parse(JSON.stringify(treeData));
            const schemasCategory = clonedRoot.children.find(child => child.name === 'Schemas');
            const systemTablesCategory = clonedRoot.children.find(child => child.name === 'System Tables');

            if (schemasCategory) {
                schemasCategory.children = schemasCategory.children
                    .map(schemaNode => {
                        const schemaNameMatches = schemaNode.name.toLowerCase().includes(filterValue);
                        const tablesCategory = schemaNode.children.find(child => child.name === 'Tables');
                        const viewsCategory = schemaNode.children.find(child => child.name === 'Views');

                        if (tablesCategory) {
                            tablesCategory.children = tablesCategory.children.filter(tableNode => {
                                return schemaNameMatches || tableNode.name.toLowerCase().includes(filterValue);
                            });
                        }

                        if (viewsCategory) {
                            viewsCategory.children = viewsCategory.children.filter(viewNode => {
                                return schemaNameMatches || viewNode.name.toLowerCase().includes(filterValue);
                            });
                        }

                        const hasTables = tablesCategory && tablesCategory.children.length > 0;
                        const hasViews = viewsCategory && viewsCategory.children.length > 0;

                        return (schemaNameMatches || hasTables || hasViews) ? schemaNode : null;
                    })
                    .filter(Boolean);
            }

            if (systemTablesCategory) {
                systemTablesCategory.children = systemTablesCategory.children.filter(tableNode =>
                    tableNode.name.toLowerCase().includes(filterValue)
                );
            }

            return clonedRoot;
        }

        function getIcon(type) {
            switch(type) {
                case 'root': return '🌐';
                case 'category': return '📁';
                case 'table_category': return '📁';
                case 'view_category': return '📁';
                case 'database': return '💾';
                case 'schema': return '📑';
                case 'table': return '📋';
                case 'view': return '👁️';
                case 'column': return '🔹';
                case 'view_definition': return '📝';
                case 'system_table': return '⚙️';
                case 'system_table_remarks': return '';
                default: return '📄';
            }
        }

        function renderNode(node) {
            let html = `<div class="tree-node" oncontextmenu="handleTreeContextMenu('${node.type}', '${node.name}', event); return false;">`;
            html += '<div class="node-content">';

            if (node.isCheckable && node.type !== 'system_table_remarks') {
                html += `<input type="checkbox" class="checkbox" onclick="event.stopPropagation();">`;
            }

            if (node.type !== 'system_table_remarks') {
                html += `<span class="icon">${getIcon(node.type)}</span>`;
            }

            html += `<span class="${node.type} name">${node.name}</span>`;
            html += '</div>';

            if (node.children && node.children.length > 0) {
                html += `
                    <div class="children">
                        ${node.children.map(child => renderNode(child)).join('')}
                    </div>
                `;
            }

            html += '</div>';
            return html;
        }

        function handleTreeContextMenu(type, name, event) {
            event.preventDefault();
            event.stopPropagation();

            const editor = document.getElementById('queryEditor');
            if (!editor) return;

            const cursorPos = editor.selectionStart;
            let insertText = '';

            // Extract clean names based on type
            if (type === 'schema') {
                insertText = name + '.';
            } else if (type === 'table') {
                insertText = name;
            } else if (type === 'column') {
                // Extract just the column name before the data type
                insertText = name.split(' - ')[0];
            }

            // Insert text at cursor position
            editor.value = editor.value.slice(0, cursorPos) + insertText + editor.value.slice(cursorPos);
            editor.focus();
            editor.selectionStart = editor.selectionEnd = cursorPos + insertText.length;
        }

        function getCheckedTableFullName() {
            const checkedBox = document.querySelector('input[type="checkbox"]:checked');
            if (!checkedBox) return null;

            let node = checkedBox.closest('.tree-node');
            const nodeElement = node.querySelector('.name');
            const nodeName = nodeElement.textContent;

            let parentNode = node.parentElement.parentElement;
            while (parentNode) {
                const categoryName = parentNode.querySelector('.name')?.textContent;
                if (categoryName === 'System Tables') {
                    return nodeName;
                }
                if (categoryName === 'Schemas') {
                    break;
                }
                parentNode = parentNode.parentElement;
            }

            let schemaNode = node.parentElement;
            while (schemaNode && !schemaNode.querySelector('.schema')) {
                schemaNode = schemaNode.parentElement;
            }
            const schemaName = schemaNode ? schemaNode.querySelector('.schema').textContent : '';

            return `${schemaName}.${nodeName}`;
        }

        // Query generation and execution
        function generateQuery() {
            const fullTableName = getCheckedTableFullName();
            if (!fullTableName) {
                alert('Please select a table or view first');
                return;
            }

            const query = `SELECT * FROM ${fullTableName} LIMIT 100;`;
            document.getElementById('queryEditor').value = query;
        }

        // Tab management
        // Tab management
let currentTabIndex = 0;
let executingQueries = false;

function parseQueries(queryText) {
    return queryText
        .split(';')
        .map(q => q.trim())
        .filter(q => q.length > 0);
}

function createTab(label, content, isError = false) {
    const tabId = `tab-${currentTabIndex++}`;

    // Create tab header
    const tabHeader = document.createElement('div');
    tabHeader.className = `tab${isError ? ' error-tab' : ''}`;
    tabHeader.setAttribute('data-tab', tabId);

    // Add click handler directly to the tab header
    tabHeader.addEventListener('click', (e) => {
        if (!e.target.classList.contains('tab-close')) {
            activateTab(tabId);
        }
    });

    tabHeader.innerHTML = `
        <span>${label}</span>
        <span class="tab-close" onclick="event.stopPropagation(); closeTab('${tabId}')">×</span>
    `;

    // Create tab content
    const tabContent = document.createElement('div');
    tabContent.className = 'tab-content';
    tabContent.id = tabId;
    tabContent.innerHTML = content;

    // Append new elements
    document.getElementById('tabHeader').appendChild(tabHeader);
    document.getElementById('tabContent').appendChild(tabContent);

    // Activate the new tab
    activateTab(tabId);
    return tabId;
}

function activateTab(tabId) {
    // Remove active class from all tabs
    const allTabs = document.querySelectorAll('.tab');
    const allContents = document.querySelectorAll('.tab-content');

    allTabs.forEach(tab => tab.classList.remove('active'));
    allContents.forEach(content => content.classList.remove('active'));

    // Add active class to selected tab and content
    const selectedTab = document.querySelector(`[data-tab="${tabId}"]`);
    const selectedContent = document.getElementById(tabId);

    if (selectedTab && selectedContent) {
        selectedTab.classList.add('active');
        selectedContent.classList.add('active');
    }
}

function closeTab(tabId) {
    const tab = document.querySelector(`[data-tab="${tabId}"]`);
    const content = document.getElementById(tabId);

    if (tab && content) {
        const isActiveTab = tab.classList.contains('active');

        // If closing active tab, find next tab to activate
        if (isActiveTab) {
            const nextTab = tab.nextElementSibling || tab.previousElementSibling;
            if (nextTab) {
                const nextTabId = nextTab.getAttribute('data-tab');
                // Remove current tab before activating next
                tab.remove();
                content.remove();
                // Activate next tab
                activateTab(nextTabId);
            }
        } else {
            // Just remove the tab if it's not active
            tab.remove();
            content.remove();
        }
    }
}

function clearAll() {
    // Clear checkboxes
    document.querySelectorAll('.checkbox:checked').forEach(checkbox => {
        checkbox.checked = false;
    });

    // Clear query editor
    document.getElementById('queryEditor').value = '';

    // Clear all tabs
    const tabHeader = document.getElementById('tabHeader');
    const tabContent = document.getElementById('tabContent');

    if (tabHeader) {
        tabHeader.innerHTML = '';
    }
    if (tabContent) {
        tabContent.innerHTML = '';
    }

    // Reset currentTabIndex
    currentTabIndex = 0;
}

function beautifySQL() {
    const editor = document.getElementById('queryEditor');
    const originalText = editor.value;

    fetch('/api/beautify_sql', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ query: originalText })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Failed to beautify SQL');
        }
        return response.json();
    })
    .then(result => {
        editor.value = result.query || originalText;
    })
    .catch(error => {
        console.error('Beautify error:', error);
        alert('Failed to beautify SQL');
    });
}

function getQueryTextToExecute() {
    const editor = document.getElementById('queryEditor');
    const fullText = editor.value;
    const selectionStart = editor.selectionStart;
    const selectionEnd = editor.selectionEnd;
    const hasSelection = selectionStart !== selectionEnd;

    if (hasSelection) {
        const selectedText = fullText.slice(selectionStart, selectionEnd);
        return {
            queryText: selectedText.trim(),
            hasSelection: true
        };
    }

    return {
        queryText: fullText.trim(),
        hasSelection: false
    };
}

async function executeQueries() {
    if (executingQueries) return;

    const { queryText, hasSelection } = getQueryTextToExecute();
    if (!queryText) {
        alert(hasSelection ? 'Please select at least one query to run' : 'Please enter at least one query');
        return;
    }

    const queries = parseQueries(queryText);
    executingQueries = true;

    for (let i = 0; i < queries.length; i++) {
        const query = queries[i];
        const startTime = performance.now();

        // Create tab and get its ID
        const tabLabel = `Query ${i + 1}`;
        const tabId = createTab(tabLabel, '<div class="loading-indicator"></div>');

        try {
            const response = await fetch('/api/execute_query', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ query })
            });

            if (!response.ok) throw new Error(await response.text());

            const result = await response.json();
            const executionTime = ((performance.now() - startTime) / 1000).toFixed(2);

            const content = `
                <div class="execution-info">Execution time: ${executionTime}s</div>
                <table class="results-table">
                    <thead>
                        <tr>${result.columns.map(col => `<th>${col}</th>`).join('')}</tr>
                    </thead>
                    <tbody>
                        ${result.rows.map(row =>
                            `<tr>${row.map(cell => `<td>${cell}</td>`).join('')}</tr>`
                        ).join('')}
                    </tbody>
                </table>
            `;

            // Update content and ensure tab remains active
            const tabContent = document.getElementById(tabId);
            if (tabContent) {
                tabContent.innerHTML = content;
                activateTab(tabId);
            }

        } catch (error) {
            console.error('Query execution error:', error);
            const errorContent = `
                <div class="execution-info">Error in query:</div>
                <pre style="white-space: pre-wrap; word-break: break-word; color: #dc3545; background: #fff5f5; border: 1px solid #dc3545; border-radius: 4px; padding: 12px; margin: 0; font-family: system-ui, -apple-system, sans-serif; font-size: 14px; line-height: 1.5; max-width: 800px;">${error.message}</pre>
            `;

            const tabContent = document.getElementById(tabId);
            if (tabContent) {
                tabContent.innerHTML = errorContent;
                activateTab(tabId);
            }
        }
    }

    executingQueries = false;
}

            // Tree node expansion
            document.addEventListener('click', (e) => {
                const node = e.target.closest('.tree-node');
                if (node && !e.target.classList.contains('checkbox')) {
                    node.classList.toggle('expanded');
                }
            });

            // Horizontal resizer functionality
            const resizer = document.getElementById('dragMe');
            const treeWrapper = document.querySelector('.tree-wrapper');
            const treePanel = document.getElementById('treePanel');
            let isResizing = false;
            let startWidth = 0;

            resizer.addEventListener('mousedown', (e) => {
                isResizing = true;
                startWidth = treePanel.offsetWidth;
                document.body.classList.add('user-select-none');
                resizer.classList.add('dragging');
            });

            document.addEventListener('mousemove', (e) => {
                if (!isResizing) return;

                const newWidth = e.clientX;
                if (newWidth >= 200 && newWidth <= 800) {
                    treePanel.style.width = `${newWidth}px`;
                    treeWrapper.style.width = `${newWidth + 5}px`;
                }
            });

            document.addEventListener('mouseup', () => {
                if (isResizing) {
                    isResizing = false;
                    document.body.classList.remove('user-select-none');
                    resizer.classList.remove('dragging');
                }
            });

            // Vertical resizer functionality
            const verticalResizer = document.getElementById('verticalDragMe');
            const querySection = document.querySelector('.query-section');
            const resultsSection = document.querySelector('.results-section');
            let isVerticalResizing = false;

            verticalResizer.addEventListener('mousedown', (e) => {
                isVerticalResizing = true;
                document.body.classList.add('user-select-none');
                verticalResizer.classList.add('dragging');
            });

            document.addEventListener('mousemove', (e) => {
                if (!isVerticalResizing) return;

                const containerRect = document.querySelector('.content-wrapper').getBoundingClientRect();
                const containerHeight = containerRect.height;
                const mouseY = e.clientY - containerRect.top;

                const queryPercentage = (mouseY / containerHeight) * 100;
                const resultsPercentage = 100 - queryPercentage;

                if (queryPercentage >= 20 && queryPercentage <= 80) {
                    querySection.style.height = `${queryPercentage}%`;
                    resultsSection.style.height = `${resultsPercentage}%`;
                }
            });

            document.addEventListener('mouseup', () => {
                if (isVerticalResizing) {
                    isVerticalResizing = false;
                    document.body.classList.remove('user-select-none');
                    verticalResizer.classList.remove('dragging');
                }
            });

            // Initial load
            // Initial load
            document.addEventListener('DOMContentLoaded', () => {
                loadTree();
                const editor = document.getElementById('queryEditor');
                editor.addEventListener('contextmenu', (e) => e.stopPropagation());
            });
        </script>
    </body>
</html>
'''

def run_server():
    try:
        PORT = 8001
        log_info(f"Starting server on port {PORT}...")
        with socketserver.TCPServer(("", PORT), DBTreeHandler) as httpd:
            print(f"Server running at http://localhost:{PORT}")
            log_info(f"Server started successfully on port {PORT}")
            httpd.serve_forever()
    except KeyboardInterrupt:
        log_info("Server shutdown initiated by user")
        print("\nShutting down server")
    except Exception as e:
        logger.error(f"Server error: {str(e)}")

if __name__ == "__main__":
    run_server()

