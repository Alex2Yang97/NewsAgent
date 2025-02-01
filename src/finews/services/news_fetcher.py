import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode

from finews.core.config import settings
from finews.models.schemas import NewsArticle

class NewsAPIException(Exception):
    """Custom exception for News API errors"""
    pass

class NewsSourceUnavailable(Exception):
    """Exception for when a news source is temporarily unavailable"""
    pass

class NewsFetcher:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.rate_limit = asyncio.Semaphore(5)  # Limit concurrent requests
        self.base_urls = {
            'newsapi': 'https://newsapi.org/v2',
            # Add other news sources here
        }
        self.api_keys = {
            'newsapi': settings.NEWS_API_KEY,
            # Add other API keys here
        }

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _make_request(self, url: str, headers: Dict[str, str]) -> Dict[str, Any]:
        """Make HTTP request with rate limiting and error handling"""
        async with self.rate_limit:
            try:
                async with self.session.get(url, headers=headers) as response:
                    if response.status == 429:  # Too Many Requests
                        retry_after = int(response.headers.get('Retry-After', 60))
                        await asyncio.sleep(retry_after)
                        return await self._make_request(url, headers)
                    
                    if response.status != 200:
                        raise NewsAPIException(
                            f"API request failed with status {response.status}: {await response.text()}"
                        )
                    
                    return await response.json()
            
            except aiohttp.ClientError as e:
                raise NewsSourceUnavailable(f"Failed to fetch news: {str(e)}")

    async def fetch_from_newsapi(
        self,
        keywords: Optional[List[str]] = None,
        companies: Optional[List[str]] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[NewsArticle]:
        """Fetch news articles from NewsAPI"""
        if not from_date:
            from_date = datetime.utcnow() - timedelta(days=1)
        if not to_date:
            to_date = datetime.utcnow()

        # Construct query parameters
        query_parts = []
        if keywords:
            query_parts.extend(keywords)
        if companies:
            query_parts.extend([f'"{company}"' for company in companies])
        
        query = ' OR '.join(query_parts) if query_parts else 'financial markets'
        
        params = {
            'q': query,
            'from': from_date.isoformat(),
            'to': to_date.isoformat(),
            'language': 'en',
            'sortBy': 'publishedAt',
            'pageSize': 100,  # Maximum allowed by NewsAPI
        }

        url = f"{self.base_urls['newsapi']}/everything?{urlencode(params)}"
        headers = {'X-Api-Key': self.api_keys['newsapi']}

        try:
            response_data = await self._make_request(url, headers)
            
            articles = []
            for article in response_data.get('articles', []):
                articles.append(
                    NewsArticle(
                        id=article['url'],  # Using URL as unique identifier
                        title=article['title'],
                        content=article['content'] or article['description'],
                        url=article['url'],
                        source=article['source']['name'],
                        published_at=datetime.fromisoformat(
                            article['publishedAt'].replace('Z', '+00:00')
                        ),
                        summary=None,  # Will be filled by news processor
                        sentiment=None,  # Will be filled by news processor
                        categories=[]  # Will be filled by news processor
                    )
                )
            
            return articles

        except Exception as e:
            raise NewsAPIException(f"Error fetching news from NewsAPI: {str(e)}")

    async def fetch_all_sources(
        self,
        keywords: Optional[List[str]] = None,
        companies: Optional[List[str]] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[NewsArticle]:
        """Fetch news from all configured sources"""
        tasks = [
            self.fetch_from_newsapi(keywords, companies, from_date, to_date),
            # Add other source fetching methods here
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out errors and flatten results
        articles = []
        for result in results:
            if isinstance(result, Exception):
                # Log the error but continue with other results
                print(f"Error fetching news: {str(result)}")
                continue
            articles.extend(result)
        
        # Sort by published date
        articles.sort(key=lambda x: x.published_at, reverse=True)
        
        return articles

    async def fetch_latest_news(
        self,
        keywords: Optional[List[str]] = None,
        companies: Optional[List[str]] = None,
    ) -> List[NewsArticle]:
        """Fetch news from the last 6 hours"""
        from_date = datetime.utcnow() - timedelta(hours=6)
        return await self.fetch_all_sources(
            keywords=keywords,
            companies=companies,
            from_date=from_date
        ) 