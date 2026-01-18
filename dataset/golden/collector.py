"""
Data collectors for golden dataset generation.

Collects documents from:
- SEC EDGAR (10-K filings)
- Local technical documentation (SHAIE/WeKnora docs)
"""

import re
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .models import Document, DocumentType


class DataCollector(ABC):
    """Base class for data collectors."""

    @abstractmethod
    def collect(self, output_dir: str, limit: Optional[int] = None) -> list[Document]:
        """Collect documents and return list of Document objects."""
        pass


class SECCollector(DataCollector):
    """
    Collect SEC 10-K filings from EDGAR database.
    
    Uses SEC EDGAR Full-Text Search API:
    https://www.sec.gov/search-filings
    """

    # Fortune 500 companies for initial dataset
    DEFAULT_COMPANIES = {
        "Microsoft": "0000789019",
        "Apple": "0000320193",
        "Tesla": "0001318605",
    }

    EDGAR_FILING_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
    EDGAR_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"

    def __init__(
        self,
        companies: Optional[dict[str, str]] = None,
        years: Optional[list[int]] = None,
        rate_limit_delay: float = 0.1,
    ):
        """
        Initialize SEC collector.

        Args:
            companies: Dict of company name -> CIK number
            years: List of years to collect (default: 2022-2024)
            rate_limit_delay: Delay between requests in seconds
        """
        self.companies = companies or self.DEFAULT_COMPANIES
        self.years = years or [2022, 2023, 2024]
        self.rate_limit_delay = rate_limit_delay
        self.session = requests.Session()
        # SEC requires User-Agent header
        self.session.headers.update({
            "User-Agent": "SHAIE-Benchmark/1.0 (benchmark@example.com)"
        })

    def collect(self, output_dir: str, limit: Optional[int] = None) -> list[Document]:
        """
        Collect 10-K filings for configured companies and years.

        Args:
            output_dir: Directory to save raw documents
            limit: Maximum number of filings to collect

        Returns:
            List of collected Document objects
        """
        documents = []
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        count = 0
        for company_name, cik in self.companies.items():
            for year in self.years:
                if limit and count >= limit:
                    break

                try:
                    doc = self._download_10k(company_name, cik, year)
                    if doc:
                        documents.append(doc)
                        # Save raw content
                        self._save_document(doc, output_path)
                        count += 1
                        print(f"Collected: {company_name} 10-K {year}")
                except Exception as e:
                    print(f"Error collecting {company_name} {year}: {e}")

                time.sleep(self.rate_limit_delay)

        return documents

    def _download_10k(self, company_name: str, cik: str, year: int) -> Optional[Document]:
        """
        Download a single 10-K filing.

        Args:
            company_name: Company name for metadata
            cik: SEC CIK number
            year: Fiscal year

        Returns:
            Document object or None if not found
        """
        # Get filing index
        index_url = f"{self.EDGAR_FILING_URL}?action=getcompany&CIK={cik}&type=10-K&dateb={year}1231&owner=exclude&count=1&output=json"

        resp = self.session.get(index_url)
        if resp.status_code != 200:
            return None

        # Parse filing list and get document URL
        # SEC returns HTML, need to parse for filing links
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Find document links in the filing table
        filing_table = soup.find("table", class_="tableFile2")
        if not filing_table:
            # Try alternative: direct filing search
            return self._download_10k_alternative(company_name, cik, year)

        # Get first 10-K filing link
        for row in filing_table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 4:
                filing_type = cells[0].get_text(strip=True)
                if "10-K" in filing_type and "10-K/A" not in filing_type:
                    doc_link = cells[1].find("a")
                    if doc_link:
                        doc_url = "https://www.sec.gov" + doc_link["href"]
                        return self._fetch_filing_content(
                            company_name, cik, year, doc_url
                        )

        return None

    def _download_10k_alternative(
        self, company_name: str, cik: str, year: int
    ) -> Optional[Document]:
        """Alternative method using direct archives URL."""
        # Construct archives URL
        cik_clean = cik.lstrip("0")
        archives_url = f"{self.EDGAR_ARCHIVES_URL}/{cik_clean}"

        # For now, return a placeholder - full implementation would
        # crawl the archives for the specific filing
        return None

    def _fetch_filing_content(
        self, company_name: str, cik: str, year: int, filing_url: str
    ) -> Optional[Document]:
        """Fetch the actual filing content."""
        time.sleep(self.rate_limit_delay)

        # Get filing index page
        resp = self.session.get(filing_url)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Find the main document (usually .htm or .txt)
        doc_table = soup.find("table", class_="tableFile")
        if not doc_table:
            return None

        for row in doc_table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 4:
                doc_type = cells[3].get_text(strip=True)
                if "10-K" in doc_type:
                    doc_link = cells[2].find("a")
                    if doc_link:
                        doc_href = doc_link["href"]
                        if not doc_href.startswith("http"):
                            doc_href = "https://www.sec.gov" + doc_href

                        time.sleep(self.rate_limit_delay)
                        doc_resp = self.session.get(doc_href)
                        if doc_resp.status_code == 200:
                            # Extract text from HTML
                            content = self._extract_text(doc_resp.text)
                            return Document(
                                id=f"sec_{cik}_{year}_10k",
                                source=doc_href,
                                doc_type=DocumentType.SEC_FILING,
                                content=content,
                                metadata={
                                    "company": company_name,
                                    "cik": cik,
                                    "year": year,
                                    "filing_type": "10-K",
                                },
                            )

        return None

    def _extract_text(self, html_content: str) -> str:
        """Extract clean text from HTML filing."""
        soup = BeautifulSoup(html_content, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Get text
        text = soup.get_text(separator="\n")

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = "\n".join(chunk for chunk in chunks if chunk)

        return text

    def _save_document(self, doc: Document, output_path: Path) -> None:
        """Save document content to file."""
        filename = f"{doc.id}.txt"
        filepath = output_path / filename
        filepath.write_text(doc.content, encoding="utf-8")


class TechDocCollector(DataCollector):
    """
    Collect technical documentation from local repositories.

    Collects markdown files from SHAIE and WeKnora projects.
    """

    DEFAULT_DOC_PATHS = [
        "/home/apexai/SHAIE/docs",
        "/home/apexai/WeKnora/docs",
    ]

    def __init__(
        self,
        doc_paths: Optional[list[str]] = None,
        extensions: Optional[list[str]] = None,
    ):
        """
        Initialize technical doc collector.

        Args:
            doc_paths: List of directories to scan for docs
            extensions: File extensions to collect (default: .md, .txt)
        """
        self.doc_paths = doc_paths or self.DEFAULT_DOC_PATHS
        self.extensions = extensions or [".md", ".txt", ".rst"]

    def collect(self, output_dir: str, limit: Optional[int] = None) -> list[Document]:
        """
        Collect documentation files from configured paths.

        Args:
            output_dir: Directory to save collected documents
            limit: Maximum number of documents to collect

        Returns:
            List of collected Document objects
        """
        documents = []
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        count = 0
        for doc_root in self.doc_paths:
            root_path = Path(doc_root)
            if not root_path.exists():
                print(f"Warning: Path does not exist: {doc_root}")
                continue

            for ext in self.extensions:
                for filepath in root_path.rglob(f"*{ext}"):
                    if limit and count >= limit:
                        break

                    try:
                        doc = self._read_document(filepath, root_path)
                        if doc and len(doc.content) > 100:  # Skip very short files
                            documents.append(doc)
                            self._save_document(doc, output_path)
                            count += 1
                            print(f"Collected: {filepath.name}")
                    except Exception as e:
                        print(f"Error reading {filepath}: {e}")

        return documents

    def _read_document(self, filepath: Path, root_path: Path) -> Optional[Document]:
        """Read a single documentation file."""
        content = filepath.read_text(encoding="utf-8", errors="ignore")

        # Determine project from path
        project = "shaie" if "SHAIE" in str(filepath) else "weknora"

        # Generate ID from relative path
        rel_path = filepath.relative_to(root_path)
        doc_id = f"doc_{project}_{rel_path.stem}_{uuid.uuid4().hex[:6]}"

        return Document(
            id=doc_id,
            source=str(filepath),
            doc_type=DocumentType.TECHNICAL_DOC if filepath.suffix == ".md" else DocumentType.MARKDOWN,
            content=content,
            metadata={
                "project": project,
                "filename": filepath.name,
                "relative_path": str(rel_path),
                "extension": filepath.suffix,
            },
        )

    def _save_document(self, doc: Document, output_path: Path) -> None:
        """Save document content to file."""
        filename = f"{doc.id}.txt"
        filepath = output_path / filename
        filepath.write_text(doc.content, encoding="utf-8")


class PDFCollector(DataCollector):
    """
    Collect and extract text from PDF documents.

    Uses WeKnora's docreader for PDF processing.
    """

    def __init__(self, pdf_paths: Optional[list[str]] = None):
        """
        Initialize PDF collector.

        Args:
            pdf_paths: List of PDF files or directories to process
        """
        self.pdf_paths = pdf_paths or ["/home/apexai/WeKnora/docs/WeKnora.pdf"]

    def collect(self, output_dir: str, limit: Optional[int] = None) -> list[Document]:
        """
        Collect and extract PDF documents.

        Note: Currently returns placeholder - full implementation would
        integrate with WeKnora's docreader/parser module.
        """
        documents = []
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        count = 0
        for pdf_path in self.pdf_paths:
            path = Path(pdf_path)
            if limit and count >= limit:
                break

            if path.is_file() and path.suffix.lower() == ".pdf":
                try:
                    doc = self._extract_pdf(path)
                    if doc:
                        documents.append(doc)
                        self._save_document(doc, output_path)
                        count += 1
                        print(f"Collected PDF: {path.name}")
                except Exception as e:
                    print(f"Error processing PDF {path}: {e}")
            elif path.is_dir():
                for pdf_file in path.glob("*.pdf"):
                    if limit and count >= limit:
                        break
                    try:
                        doc = self._extract_pdf(pdf_file)
                        if doc:
                            documents.append(doc)
                            self._save_document(doc, output_path)
                            count += 1
                            print(f"Collected PDF: {pdf_file.name}")
                    except Exception as e:
                        print(f"Error processing PDF {pdf_file}: {e}")

        return documents

    def _extract_pdf(self, pdf_path: Path) -> Optional[Document]:
        """
        Extract text from PDF using available methods.

        Falls back to basic text extraction if docreader unavailable.
        """
        try:
            # Try pdfplumber first (commonly available)
            import pdfplumber

            text_parts = []
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)

            content = "\n\n".join(text_parts)

        except ImportError:
            # Fallback: try PyPDF2
            try:
                from PyPDF2 import PdfReader

                reader = PdfReader(pdf_path)
                text_parts = []
                for page in reader.pages:
                    text_parts.append(page.extract_text())
                content = "\n\n".join(text_parts)

            except ImportError:
                print("No PDF library available. Install pdfplumber or PyPDF2.")
                return None

        if not content or len(content) < 100:
            return None

        doc_id = f"pdf_{pdf_path.stem}_{uuid.uuid4().hex[:6]}"

        return Document(
            id=doc_id,
            source=str(pdf_path),
            doc_type=DocumentType.PDF,
            content=content,
            metadata={
                "filename": pdf_path.name,
                "file_size": pdf_path.stat().st_size,
            },
        )

    def _save_document(self, doc: Document, output_path: Path) -> None:
        """Save document content to file."""
        filename = f"{doc.id}.txt"
        filepath = output_path / filename
        filepath.write_text(doc.content, encoding="utf-8")
