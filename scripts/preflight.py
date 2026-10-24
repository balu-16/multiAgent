"""Read-only credential/connectivity checks; never prints credential values."""
import concurrent.futures
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request


def read_env():
    values = {}
    for line in (Path(__file__).resolve().parents[1] / ".env").read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    return values


def main():
    values = read_env()
    supabase = values["SUPABASE_URL"].rstrip("/")
    service_key = values.get("SUPABASE_SERVICE_ROLE_KEY") or values["SUPABASE_SECRET_KEY"]
    jobs = [
        ("groq", "https://api.groq.com/openai/v1/models", {"Authorization": "Bearer " + values["GROQ_API_KEY"]}),
        ("gemini", "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash", {"x-goog-api-key": values["GEMINI_API_KEY"]}),
        ("supabase", supabase + "/rest/v1/backchannel_users?select=id&limit=1", {"apikey": service_key, "Authorization": "Bearer " + service_key}),
    ]
    if values["REDIS_URL"].startswith("https://"):
        jobs.append(("redis", values["REDIS_URL"].rstrip("/") + "/ping", {"Authorization": "Bearer " + values["REDIS_TOKEN"]}))
    if values.get("SUPABASE_ANON_KEY"):
        anon = values["SUPABASE_ANON_KEY"]
        jobs.append(("supabase_anon_denied", supabase + "/rest/v1/backchannel_users?select=id&limit=1", {"apikey": anon, "Authorization": "Bearer " + anon}))

    def check(job):
        label, url, headers = job
        result = {"service": label, "ok": False}
        try:
            headers = {"User-Agent": "Backchannel/1.0", **headers}
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as response:
                data = json.load(response)
                result["http_status"] = response.status
                result["ok"] = True
                if label == "groq":
                    result["ok"] = any(m.get("id") == "openai/gpt-oss-20b" for m in data.get("data", []))
                elif label == "gemini":
                    result["ok"] = data.get("name") == "models/gemini-2.5-flash"
                elif label == "redis":
                    result["ok"] = data.get("result") == "PONG"
                elif label == "supabase_anon_denied":
                    result["ok"] = False
        except urllib.error.HTTPError as error:
            result["http_status"] = error.code
            if label == "supabase_anon_denied":
                result["ok"] = error.code in (401, 403)
        except Exception as error:
            result["error_type"] = type(error).__name__
        return result

    if len(sys.argv) > 1:
        jobs = [job for job in jobs if job[0] in sys.argv[1:]]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(check, jobs))
    print(json.dumps({"checks": results}, indent=2))
    return 0 if all(result["ok"] for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
