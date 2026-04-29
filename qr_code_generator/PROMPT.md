# QR Code Generator Prototype

## System Requirements

Build a dynamic QR code system where:
- Users submit a long URL and get back a short URL token + QR code image
- The QR code encodes a short URL that redirects (302) to the original URL via your server
- Users can modify the target URL after QR code creation
- Users can delete a QR code (soft delete)
- Users can optionally set an expiration timestamp on create or update
- Deleted or expired links return appropriate HTTP status codes
- URL validation: format check, normalization, malicious URL blocking

## Design Questions

Answer these before you start coding:

1. **Static vs Dynamic QR Code:** Why does this system use dynamic QR codes (encode short URL) instead of static (encode original URL directly)? When would you choose static instead?

```
When we use a dynamic QR code, the user first visit our service (shortened URL) before redirected to the original URL. This let us be able to track and calculate the statistic. But the trade-off is longer response time due to redirection. If we intent to provide an simple, quick service for QR code generation, we can use static URL because we don't need to track and generate statistic. This makes the user see the original URL faster.
```

2. **Token Generation:** How will you generate short URL tokens? What happens when two different URLs produce the same token? How does collision probability change as the number of tokens grows?

```
I think we can use hash function to generate URL token. The QR token is regarded as QR code unique id, so when there're different URLs matching a same token, we might get unexpected result. For example, trying to get/update/delete URL A but receive URL B. As the total amount of tokens grows, the collision probability become higher. The way to prevent from collision, we can hash a combined key such as `(user_id, url, timestamp)` so that the collision probability would be minimized.
```

3. **Redirect Strategy:** Why 302 (temporary) instead of 301 (permanent)? What are the trade-offs for analytics, URL modification, and latency?

```
When we choose 301 (permanent), browser would cache this mapping. This makes the client only hit our shortened URL at first time. Which made us lost our real tracking data because browser would directly goes to original URL in the later calls. This also cause a URL modification failed because we're unable to tell client browser to clear their cache. So even if we modified the original URL, the client still browse to old URL in their cache.

While 302 would visit shortened URL -redirect-> original URL at every visit. This cause a longer latency but solve the problems above.
```

4. **URL Normalization:** What normalization rules do you need? Why is `http://Example.com/` and `https://example.com` potentially the same URL?

```
We might need following rules:
- remove unnecessary trailing slash
- lowercase the hostname because the domain name is case-insensitive
- remove default port (:80 for HTTP / :443 for HTTPs)

and we should note that the same URL starts with `http://` and `https://` might be different site. So we can't treat them as same.
```

5. **Error Semantics:** What should happen when someone scans a deleted link vs a non-existent link? Should the HTTP status codes be different?

```
In my opinion, we should send 204 for deleted link, telling the client that this URL do exist, but deleted. And should return 404 for non-existent link. So that the client knows what happened easily and clearly.
```

## Verification

Your prototype should pass all of these:

```bash
# Create a QR code
curl -X POST http://localhost:8000/api/qr/create \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
# → 200, returns {"token": "...", "short_url": "...", "qr_code_url": "...", "original_url": "..."}

# Redirect
curl -o /dev/null -w "%{http_code}" http://localhost:8000/r/{token}
# → 302

# Get info
curl http://localhost:8000/api/qr/{token}
# → 200, returns token metadata

# Update target URL
curl -X PATCH http://localhost:8000/api/qr/{token} \
  -H "Content-Type: application/json" \
  -d '{"url": "https://new-url.com"}'
# → 200

# Redirect now goes to new URL
curl -o /dev/null -w "%{redirect_url}" http://localhost:8000/r/{token}
# → https://new-url.com

# Delete
curl -X DELETE http://localhost:8000/api/qr/{token}
# → 200

# Redirect after delete
curl -o /dev/null -w "%{http_code}" http://localhost:8000/r/{token}
# → 410

# Non-existent token
curl -o /dev/null -w "%{http_code}" http://localhost:8000/r/INVALID
# → 404

# QR code image
# (create a new one first, then)
curl -o /dev/null -w "%{http_code} %{content_type}" http://localhost:8000/api/qr/{token}/image
# → 200 image/png

# Analytics
curl http://localhost:8000/api/qr/{token}/analytics
# → 200, returns {"token": "...", "total_scans": N, "scans_by_day": [...]}
```

## Suggested Tech Stack

Python + FastAPI recommended, but you may use any language/framework.
