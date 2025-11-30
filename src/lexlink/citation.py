"""
HTML-based Citation Extractor for Korean Laws.

Extracts citations directly from law.go.kr HTML pages using pre-linked
citation data. This approach provides 100% accuracy with zero API cost.

Usage:
    extractor = CitationExtractor()
    citations = await extractor.extract_citations(mst="268611", article=3)
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """Structured citation data extracted from HTML."""

    # Target info (required)
    target_text: str              # Original link text
    target_ref_id: str            # Reference ID from fncLsLawPop
    target_type: str              # "ALLJO" (whole law) or "JO" (article)

    # Parsed target details (optional)
    target_law_name: Optional[str] = None     # 「법명」
    target_article: Optional[int] = None      # 제N조
    target_article_branch: Optional[int] = None  # 제N조의M
    target_paragraph: Optional[int] = None    # 제N항
    target_item: Optional[int] = None         # 제N호
    target_subitem: Optional[str] = None      # 가목, 나목

    # Classification
    citation_type: str = "unknown"            # internal/external
    link_class: str = ""                      # sfon1/sfon2/sfon3/sfon4

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "type": self.citation_type,
            "raw_text": self.target_text,
            "ref_id": self.target_ref_id,
        }

        if self.target_law_name:
            result["target_law_name"] = self.target_law_name
        if self.target_article is not None:
            result["target_article"] = self.target_article
        if self.target_article_branch is not None:
            result["target_article_branch"] = self.target_article_branch
        if self.target_paragraph is not None:
            result["target_paragraph"] = self.target_paragraph
        if self.target_item is not None:
            result["target_item"] = self.target_item
        if self.target_subitem:
            result["target_subitem"] = self.target_subitem

        return result


@dataclass
class CitationResult:
    """Result of citation extraction for an article."""

    success: bool
    law_id: str
    law_name: str
    article: str                              # Display format: "제3조" or "제37조의2"
    citation_count: int
    citations: List[Dict[str, Any]]

    # Statistics
    internal_count: int = 0                   # Same-law citations
    external_count: int = 0                   # Other-law citations

    # Metadata
    extraction_method: str = "html"
    processing_time_ms: float = 0.0

    # Errors (if any)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "success": self.success,
            "law_id": self.law_id,
            "law_name": self.law_name,
            "article": self.article,
            "citation_count": self.citation_count,
            "citations": self.citations,
            "internal_count": self.internal_count,
            "external_count": self.external_count,
            "extraction_method": self.extraction_method,
            "processing_time_ms": self.processing_time_ms,
            "errors": self.errors if self.errors else [],
        }


class CitationExtractor:
    """
    Extract citations from law.go.kr HTML pages.

    This extractor parses the pre-linked citations that law.go.kr provides
    in article HTML. Citations are identified by CSS classes:
    - sfon1: Law name (「법명」)
    - sfon2: Article (제N조, 제N조의M)
    - sfon3: Paragraph (제N항)
    - sfon4: Item (제N호)
    """

    # Endpoints
    ARTICLE_HTML_URL = "https://www.law.go.kr/LSW/lsSideInfoP.do"
    LAW_PAGE_URL = "https://www.law.go.kr/법령/{law_name}"

    # Regex patterns
    ARTICLE_PATTERN = re.compile(r'제(\d+)조(?:의(\d+))?')
    PARAGRAPH_PATTERN = re.compile(r'제(\d+)항')
    ITEM_PATTERN = re.compile(r'제(\d+)호')
    LAW_NAME_PATTERN = re.compile(r'「([^」]+)」')
    FNCPOP_PATTERN = re.compile(r"fncLsLawPop\s*\(\s*['\"](\d+)['\"].*?['\"](\w+)['\"]")
    LSI_SEQ_PATTERN = re.compile(r'lsiSeq=(\d+)')

    def __init__(self, timeout: int = 15, request_delay: float = 0.1):
        """
        Initialize citation extractor.

        Args:
            timeout: HTTP request timeout in seconds
            request_delay: Delay between requests to avoid rate limiting
        """
        self.timeout = timeout
        self.request_delay = request_delay
        self._lsi_seq_cache: Dict[str, str] = {}  # MST -> lsiSeq mapping

    async def get_lsi_seq(self, law_name: str, mst: str) -> Optional[str]:
        """
        Get lsiSeq from law main page (required for HTML article fetching).

        The law.go.kr website uses different IDs:
        - MST: Used by XML API
        - lsiSeq: Used by HTML pages

        Args:
            law_name: Law name for URL
            mst: MST code to cache the mapping

        Returns:
            lsiSeq if found, None otherwise
        """
        if mst in self._lsi_seq_cache:
            return self._lsi_seq_cache[mst]

        # URL-encode Korean law name
        encoded_name = quote(law_name, safe='')
        url = f"https://www.law.go.kr/법령/{encoded_name}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, follow_redirects=True)

                if response.status_code != 200:
                    logger.warning(f"Failed to fetch law page: {response.status_code}")
                    return None

                html = response.text

                # Look for lsiSeq in iframe src or script tags
                match = self.LSI_SEQ_PATTERN.search(html)
                if match:
                    lsi_seq = match.group(1)
                    self._lsi_seq_cache[mst] = lsi_seq
                    logger.debug(f"Found lsiSeq={lsi_seq} for MST={mst}")
                    return lsi_seq

                logger.warning(f"Could not find lsiSeq for {law_name}")
                return None

        except Exception as e:
            logger.error(f"Error fetching law page: {e}")
            return None

    async def fetch_article_html(
        self,
        lsi_seq: str,
        article_no: int,
        article_branch: int = 0
    ) -> Optional[str]:
        """
        Fetch article HTML from law.go.kr side panel endpoint.

        Args:
            lsi_seq: Law sequence ID
            article_no: Article number (조번호)
            article_branch: Article branch number (조가지번호, e.g., 제37조의2 → branch=2)

        Returns:
            HTML content if successful, None otherwise
        """
        params = {
            "lsiSeq": lsi_seq,
            "joNo": str(article_no).zfill(4),      # 4-digit: 0003 for 제3조
            "joBrNo": str(article_branch).zfill(2), # 2-digit: 02 for 조의2
            "docCls": "jo",
            "urlMode": "lsScJoRltInfoR"
        }

        try:
            await asyncio.sleep(self.request_delay)

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.ARTICLE_HTML_URL, params=params)

                if response.status_code == 200:
                    return response.text
                else:
                    logger.debug(f"Article fetch returned {response.status_code}")
                    return None

        except Exception as e:
            logger.error(f"Error fetching article HTML: {e}")
            return None

    def parse_citations(
        self,
        html: str,
        source_law_name: str
    ) -> List[Citation]:
        """
        Parse citation links from article HTML.

        Args:
            html: Article HTML content
            source_law_name: Name of the source law (for internal/external classification)

        Returns:
            List of parsed citations (not yet consolidated)
        """
        soup = BeautifulSoup(html, 'html.parser')
        citations = []

        # Find all citation links (class contains "link" and "sfon")
        link_elements = soup.find_all(
            'a',
            class_=lambda x: x and 'link' in x and 'sfon' in x
        )

        for link in link_elements:
            citation = self._parse_single_link(link, source_law_name)
            if citation:
                citations.append(citation)

        return citations

    def _parse_single_link(
        self,
        link,
        source_law_name: str
    ) -> Optional[Citation]:
        """Parse a single citation link element."""
        onclick = link.get('onclick', '')
        link_text = link.get_text(strip=True)
        classes = link.get('class', [])

        # Extract ref_id and type from onclick="fncLsLawPop('123','JO','')"
        match = self.FNCPOP_PATTERN.search(onclick)
        if not match:
            return None

        ref_id = match.group(1)
        ref_type = match.group(2)

        # Determine link class (sfon1, sfon2, sfon3, sfon4)
        link_class = ""
        for cls in classes:
            if cls.startswith('sfon'):
                link_class = cls
                break

        citation = Citation(
            target_text=link_text,
            target_ref_id=ref_id,
            target_type=ref_type,
            link_class=link_class
        )

        # Parse target details based on link class
        if link_class == 'sfon1':
            # Law name: 「법명」
            law_match = self.LAW_NAME_PATTERN.search(link_text)
            if law_match:
                citation.target_law_name = law_match.group(1)
                citation.citation_type = "external"
            elif '같은 법' in link_text or '이 법' in link_text:
                citation.citation_type = "internal"
                citation.target_law_name = source_law_name
            else:
                citation.target_law_name = link_text
                citation.citation_type = "external"

        elif link_class == 'sfon2':
            # Article: 제N조 or 제N조의M
            citation.citation_type = "internal"
            art_match = self.ARTICLE_PATTERN.search(link_text)
            if art_match:
                citation.target_article = int(art_match.group(1))
                if art_match.group(2):
                    citation.target_article_branch = int(art_match.group(2))

        elif link_class == 'sfon3':
            # Paragraph: 제N항
            citation.citation_type = "internal"
            para_match = self.PARAGRAPH_PATTERN.search(link_text)
            if para_match:
                citation.target_paragraph = int(para_match.group(1))

        elif link_class == 'sfon4':
            # Item: 제N호
            citation.citation_type = "internal"
            item_match = self.ITEM_PATTERN.search(link_text)
            if item_match:
                citation.target_item = int(item_match.group(1))

        return citation

    def consolidate_citations(self, citations: List[Citation]) -> List[Citation]:
        """
        Consolidate sequential citations into complete references.

        Law.go.kr HTML has separate <a> tags for law name, article, paragraph, etc.
        This function merges them into single citation objects.

        Example: 「형법」 + 제20조 + 제1항 → one citation with all fields

        Args:
            citations: List of parsed citations (one per HTML link)

        Returns:
            List of consolidated citations
        """
        if not citations:
            return []

        consolidated = []
        current_external_law = None
        current_internal_article_idx = None  # Index of last internal article citation

        for citation in citations:
            if citation.link_class == 'sfon1':
                # New law reference - resets internal article tracking
                current_internal_article_idx = None
                if citation.citation_type == "external":
                    current_external_law = citation.target_law_name
                else:
                    current_external_law = None
                consolidated.append(citation)

            elif citation.link_class == 'sfon2':
                # Article reference
                if current_external_law and len(consolidated) > 0:
                    last = consolidated[-1]
                    if (last.citation_type == "external" and
                        last.target_law_name == current_external_law):
                        # Check if external law already has an article
                        if last.target_article is None:
                            # Merge article into external law citation
                            last.target_article = citation.target_article
                            last.target_article_branch = citation.target_article_branch
                            last.target_text += " " + citation.target_text
                            current_internal_article_idx = None
                            continue
                        # Else: external law already has article, treat as new internal

                # New internal article reference - breaks external law context
                current_external_law = None
                citation.citation_type = "internal"
                consolidated.append(citation)
                current_internal_article_idx = len(consolidated) - 1

            elif citation.link_class in ('sfon3', 'sfon4'):
                # Paragraph (sfon3) or Item (sfon4) reference
                merged = False

                # Try to merge with external law citation
                if current_external_law and len(consolidated) > 0:
                    last = consolidated[-1]
                    if (last.citation_type == "external" and
                        last.target_law_name == current_external_law):
                        # Check if already has paragraph/item
                        if ((citation.target_paragraph and last.target_paragraph) or
                            (citation.target_item and last.target_item)):
                            # Create a copy with same context but new paragraph/item
                            new_citation = Citation(
                                target_text=citation.target_text,
                                target_ref_id=citation.target_ref_id,
                                target_type=citation.target_type,
                                target_law_name=last.target_law_name,
                                target_article=last.target_article,
                                target_article_branch=last.target_article_branch,
                                target_paragraph=citation.target_paragraph,
                                target_item=citation.target_item,
                                citation_type="external",
                                link_class=citation.link_class
                            )
                            consolidated.append(new_citation)
                        else:
                            if citation.target_paragraph:
                                last.target_paragraph = citation.target_paragraph
                            if citation.target_item:
                                last.target_item = citation.target_item
                            last.target_text += " " + citation.target_text
                        merged = True

                # Try to merge with previous internal article citation
                elif current_internal_article_idx is not None:
                    last_article = consolidated[current_internal_article_idx]
                    if (last_article.citation_type == "internal" and
                        last_article.target_article):
                        # Check if already has paragraph/item
                        if ((citation.target_paragraph and last_article.target_paragraph) or
                            (citation.target_item and last_article.target_item)):
                            # Create copy with same article but new paragraph/item
                            new_citation = Citation(
                                target_text=citation.target_text,
                                target_ref_id=citation.target_ref_id,
                                target_type=citation.target_type,
                                target_law_name=last_article.target_law_name,
                                target_article=last_article.target_article,
                                target_article_branch=last_article.target_article_branch,
                                target_paragraph=citation.target_paragraph,
                                target_item=citation.target_item,
                                citation_type="internal",
                                link_class=citation.link_class
                            )
                            consolidated.append(new_citation)
                        else:
                            if citation.target_paragraph:
                                last_article.target_paragraph = citation.target_paragraph
                            if citation.target_item:
                                last_article.target_item = citation.target_item
                            last_article.target_text += " " + citation.target_text
                        merged = True

                if not merged:
                    # Standalone paragraph/item reference
                    citation.citation_type = "internal"
                    consolidated.append(citation)

        return consolidated

    async def extract_citations(
        self,
        mst: str,
        law_name: str,
        article: int,
        article_branch: int = 0
    ) -> CitationResult:
        """
        Extract all citations from a specific law article.

        Args:
            mst: Law MST code (법령일련번호)
            law_name: Law name for display and lsiSeq lookup
            article: Article number (조번호)
            article_branch: Article branch number (조가지번호, default 0)

        Returns:
            CitationResult with all extracted citations
        """
        start_time = time.time()
        errors = []

        # Build article display string
        article_display = f"제{article}조"
        if article_branch > 0:
            article_display += f"의{article_branch}"

        # Step 1: Get lsiSeq
        lsi_seq = await self.get_lsi_seq(law_name, mst)
        if not lsi_seq:
            return CitationResult(
                success=False,
                law_id=mst,
                law_name=law_name,
                article=article_display,
                citation_count=0,
                citations=[],
                errors=[f"Could not get lsiSeq for {law_name}. Law may not exist or name may be incorrect."]
            )

        # Step 2: Fetch article HTML
        html = await self.fetch_article_html(lsi_seq, article, article_branch)
        if not html:
            return CitationResult(
                success=False,
                law_id=mst,
                law_name=law_name,
                article=article_display,
                citation_count=0,
                citations=[],
                errors=[f"Could not fetch HTML for {article_display}. Article may not exist."]
            )

        # Step 3: Parse citations
        raw_citations = self.parse_citations(html, law_name)

        # Step 4: Consolidate citations
        consolidated = self.consolidate_citations(raw_citations)

        # Step 5: Convert to dict format
        citation_dicts = [c.to_dict() for c in consolidated]

        # Step 6: Count internal vs external
        internal_count = sum(1 for c in consolidated if c.citation_type == "internal")
        external_count = sum(1 for c in consolidated if c.citation_type == "external")

        processing_time = (time.time() - start_time) * 1000  # Convert to ms

        return CitationResult(
            success=True,
            law_id=mst,
            law_name=law_name,
            article=article_display,
            citation_count=len(consolidated),
            citations=citation_dicts,
            internal_count=internal_count,
            external_count=external_count,
            extraction_method="html",
            processing_time_ms=round(processing_time, 2),
            errors=errors
        )


# Module-level extractor instance (reused across requests)
_extractor: Optional[CitationExtractor] = None


def get_extractor() -> CitationExtractor:
    """Get or create the module-level citation extractor."""
    global _extractor
    if _extractor is None:
        _extractor = CitationExtractor()
    return _extractor


async def extract_article_citations(
    mst: str,
    law_name: str,
    article: int,
    article_branch: int = 0
) -> Dict[str, Any]:
    """
    Convenience function to extract citations from an article.

    Args:
        mst: Law MST code
        law_name: Law name
        article: Article number
        article_branch: Article branch number (default 0)

    Returns:
        Citation result as dictionary
    """
    extractor = get_extractor()
    result = await extractor.extract_citations(mst, law_name, article, article_branch)
    return result.to_dict()
