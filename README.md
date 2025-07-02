# Project Setup and Usage

This project contains a Python server that can be run locally and integrated with Cline as a remote MCP server.

## 0. Create .env file

If your project requires environment variables (e.g., API keys, database credentials), create a `.env` file in the root directory of the project.

Example `.env` content:

```
GOOGLE_API_KEY="<your-google-api-key-here>"
COHERE_API_KEY="<your-cohere-api-key-here>"
```

**Note**: Do not commit your `.env` file to version control as it may contain sensitive information.

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

## 4. Switching to Google Gemini API

By default, some tools may use other API providers. If you wish to use Google's Gemini models, you will need to perform the following steps:

1.  **Ensure you have a `GOOGLE_API_KEY`** set in your `.env` file, as described in Step 0.
2.  **Manually edit the tool files.** Some tool files (e.g., `static_tools/file_analysis_tool.py`, `static_tools/meta_tool.py`) contain commented-out code for using `ChatGoogleGenerativeAI`. You will need to:
    *   Comment out the line that initializes the current LLM (e.g., `ChatOpenAI`).
    *   Uncomment the line that initializes `ChatGoogleGenerativeAI`.

    **Example in `static_tools/file_analysis_tool.py`:**

    ```python
    # Comment out the existing LLM
    # llm = ChatOpenAI(...)

    # Uncomment the Google Gemini LLM
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0, google_api_key=GOOGLE_API_KEY)
    ```
3.  **Restart the server.** After making these changes, restart the Python server (`python server.py`) for the changes to take effect.
