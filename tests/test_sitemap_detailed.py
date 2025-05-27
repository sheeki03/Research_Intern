import asyncio
import httpx
import gzip
import zlib
import io

async def debug_sitemap():
    url = "https://docs.loopfi.xyz/sitemap.xml"
    
    async with httpx.AsyncClient(follow_redirects=True, timeout=25.0) as client:
        response = await client.get(url)
        
        print(f"Status: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        print(f"Content length: {len(response.content)} bytes")
        print(f"Text length: {len(response.text)} chars")
        
        # Show raw content (first 200 bytes)
        print(f"Raw content (first 200 bytes): {response.content[:200]}")
        
        # Show text content (first 200 chars)
        print(f"Text content (first 200 chars): {repr(response.text[:200])}")
        
        # Try different decompression methods
        raw_content = response.content
        
        print("\n--- Trying gzip decompression ---")
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw_content)) as gz_file:
                decompressed = gz_file.read().decode('utf-8')
                print(f"Gzip decompressed length: {len(decompressed)}")
                print(f"Gzip content preview: {decompressed[:500]}")
        except Exception as e:
            print(f"Gzip failed: {e}")
        
        print("\n--- Trying zlib decompression ---")
        try:
            decompressed = zlib.decompress(raw_content).decode('utf-8')
            print(f"Zlib decompressed length: {len(decompressed)}")
            print(f"Zlib content preview: {decompressed[:500]}")
        except Exception as e:
            print(f"Zlib failed: {e}")
        
        print("\n--- Trying raw deflate decompression ---")
        try:
            decompressed = zlib.decompress(raw_content, -15).decode('utf-8')
            print(f"Raw deflate decompressed length: {len(decompressed)}")
            print(f"Raw deflate content preview: {decompressed[:500]}")
        except Exception as e:
            print(f"Raw deflate failed: {e}")

if __name__ == "__main__":
    asyncio.run(debug_sitemap()) 