# delivery

Entry points: `http/` (Flask blueprints per feature), `webhooks/` (signature-verified provider callbacks), `worker/` (job loop), `middleware.py` (request ID, auth context, access log), `errors.py` (error envelope mapping).
