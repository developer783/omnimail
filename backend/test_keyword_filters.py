import httpx
from app.security import create_access_token

def test_keyword_filtering_flow():
    token = create_access_token({"sub": "admin"})
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(base_url="http://127.0.0.1:8000") as client:
        print("--- 1. Testing GET /filters (initial state) ---")
        get_resp = client.get("/filters", headers=headers)
        print(f"GET /filters status: {get_resp.status_code}, count: {len(get_resp.json())}")

        print("\n--- 2. Creating Keyword Filter ('security' in subject) ---")
        post_resp = client.post("/filters", headers=headers, json={"keyword": "security", "field": "subject"})
        print(f"POST /filters status: {post_resp.status_code}")
        created_filter = post_resp.json()
        print(f"  Created Filter: ID={created_filter['id']} | Keyword='{created_filter['keyword']}' | Field='{created_filter['field']}'")

        print("\n--- 3. Triggering Sync with Active Filter ---")
        sync_resp = client.post("/emails/sync", headers=headers)
        print(f"POST /emails/sync status: {sync_resp.status_code} | Message: {sync_resp.json().get('message')}")

        print("\n--- 4. Checking Ingested Emails ---")
        emails_resp = client.get("/emails?folder=inbox", headers=headers)
        data = emails_resp.json()
        print(f"Total Inbox Items returned: {len(data['items'])}")
        print(f"Active Filters returned in metadata: {data.get('filters')}")

        print("\n--- 5. Deleting Keyword Filter ---")
        del_resp = client.delete(f"/filters/{created_filter['id']}", headers=headers)
        print(f"DELETE /filters/{created_filter['id']} status: {del_resp.status_code} | Msg: {del_resp.json().get('message')}")

        print("\n--- 6. Verifying Reversion to Standard 24h Ingestion ---")
        emails_after_del = client.get("/emails?folder=inbox", headers=headers)
        print(f"Total Inbox Items after removing filter: {len(emails_after_del.json()['items'])}")

if __name__ == "__main__":
    test_keyword_filtering_flow()
