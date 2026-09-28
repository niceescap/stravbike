# Spécification de l'API Conversational

## Endpoint: POST /api/conversation/message
Envoyer un message à l'assistant IA.

### Request Body
```json
{
  "athlete_id": 12345,
  "message": "string",
  "session_id": "uuid-string"
}
```

### Response
```json
{
  "response": "string",
  "artifacts_created": [
    {
      "id": "uuid-string",
      "title": "string",
      "type": "training_plan|analysis|recommendation"
    }
  ],
  "next_session_id": "uuid-string"
}
```

## Endpoint: GET /api/conversation/history/{session_id}
Récupérer l'historique d'une session de conversation.

### Response
```json
{
  "messages": [
    {
      "role": "user|assistant",
      "content": "string",
      "timestamp": "iso-date-string"
    }
  ]
}
```

## Endpoint: GET /api/athlete/{athlete_id}/artifacts
Récupérer tous les artefacts d'un athlète.

### Response
```json
{
  "artifacts": [
    {
      "id": "uuid-string",
      "title": "string",
      "type": "training_plan|analysis|recommendation",
      "created_at": "iso-date-string"
    }
  ]
}
```

## Endpoint: GET /api/artifact/{artifact_id}
Récupérer le contenu d'un artefact.

### Response
```json
{
  "id": "uuid-string",
  "title": "string",
  "content": "markdown-string",
  "type": "training_plan|analysis|recommendation",
  "created_at": "iso-date-string"
}
```