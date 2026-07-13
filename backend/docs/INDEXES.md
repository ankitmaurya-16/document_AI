# MongoDB indexes

The backend creates these on first DB call (`rag/database.py::_ensure_indexes`):

| Collection  | Index                                        | Why                                              |
|-------------|----------------------------------------------|--------------------------------------------------|
| `users`     | `email` (unique)                             | login lookup, prevents duplicate registrations   |
| `chats`     | `(userId ASC, updatedAt DESC)`               | sidebar "recent chats" query                     |
| `chats`     | `userId`                                     | simple per-user filter                           |
| `chats`     | `createdAt`                                  | admin / analytics                                |
| `documents` | `(userId ASC, uploadedAt DESC)`              | document management page                        |
| `feedback`  | `(chatId ASC, messageTimestamp ASC)`         | upsert on vote toggle, list per chat            |
| `feedback`  | `userId`                                     | per-user analytics                               |

## Verifying the hot-path query uses the index

The Sidebar query is

```js
db.chats.find({userId: "<id>"}).sort({updatedAt: -1}).limit(50)
```

`explain("executionStats")` against a populated collection shows:

```json
{
  "executionStats": {
    "nReturned": 50,
    "totalKeysExamined": 50,
    "totalDocsExamined": 50,
    "executionStages": {
      "stage": "LIMIT",
      "inputStage": {
        "stage": "FETCH",
        "inputStage": {
          "stage": "IXSCAN",
          "keyPattern": { "userId": 1, "updatedAt": -1 },
          "indexName": "userId_1_updatedAt_-1",
          "direction": "forward"
        }
      }
    }
  }
}
```

Key points:
- `stage: IXSCAN` (not `COLLSCAN`) — the compound index is being used.
- `totalKeysExamined == nReturned` — no wasted scanning.
- `direction: forward` on `updatedAt: -1` works because the index was created
  `DESCENDING` on `updatedAt`, so Mongo walks it forward to produce the sort.

## Reproducing locally

```bash
# with docker compose up (or any Mongo):
docker exec -it $(docker ps -qf name=mongo) mongosh rag_chat_app --eval '
  db.chats.find({userId: "000000000000000000000001"})
    .sort({updatedAt: -1}).limit(50)
    .explain("executionStats")
'
```

If you see `COLLSCAN` instead of `IXSCAN`, the index wasn't created — restart
the backend so `_ensure_indexes` runs, or re-run it manually:

```js
db.chats.createIndex({userId: 1, updatedAt: -1})
db.documents.createIndex({userId: 1, uploadedAt: -1})
db.feedback.createIndex({chatId: 1, messageTimestamp: 1})
```
