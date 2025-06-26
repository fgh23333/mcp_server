# Project Setup and Usage

This project contains a Python server that can be run locally and integrated with Cline as a remote MCP server.

## 1. Install Dependencies

Ensure you have Python and pip installed. Then, install the required Python dependencies using the `requirements.txt` file:

```bash
pip install -r requirements.txt
```

## 2. Run the Python Server

Start the local server by executing the `server.py` script:

```bash
python server.py
```

This will start the server, typically on `http://localhost:8000`. Please ensure it works.

## 3. Configure Remote Server in Cline

To use the tools provided by this server within Cline, you need to configure it as a remote MCP server:

1.  Open Cline settings. You can usually find this by clicking on the gear icon or navigating through the settings menu in your IDE (e.g., VS Code).
2.  Look for "MCP servers".
3.  Add a new remote server configuration with the following details:
    *   **Server Name**: `Demo`
    *   **Server URL**: `http://localhost:8000/sse`

After saving these settings, Cline should be able to connect to your local server and expose its tools.
