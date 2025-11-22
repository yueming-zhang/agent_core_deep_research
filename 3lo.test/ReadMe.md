## 1_local_direct.py
- This app retrieves my google calendar event by running directly from local (no agent core, no agent identity)
- Before running the file, need to start the oauth2_callback_server.py so it listen to the callback
- this works fine on devcontainer if the port 9090 is set to public and portfoward is setup as shown here in the devcontainer.json:
```
"forwardPorts": [8501, 8080, 9090],

  "portsAttributes": {
    "8080": {
      "label": "OAuth2 Callback Server 1",
      "onAutoForward": "notify",
      "visibility": "public",
      "protocol": "https"
    },
    "9090": {
      "label": "OAuth2 Callback Server",
      "onAutoForward": "notify",
      "visibility": "public",
      "protocol": "https"
    },
    "8501": {
      "label": "Streamlit App",
      "onAutoForward": "notify",
      "visibility": "public"
    }

```

- Google OAuth client need to authorize this callback: http://localhost:9090/oauth2/callback

- when run the 1_local_direct.py, manual copy and past the redirect URL is required