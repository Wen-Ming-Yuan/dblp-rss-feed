from dataclasses import dataclass, field
from typing import Optional, List
from datetime import date


@dataclass
class Paper:
    title: str
    doi: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    pub_date: Optional[date] = None
    venue_short: str = ""
    venue_full: str = ""
    ccf_level: str = "A"
    ccf_category: str = ""
    url: str = ""
    abstract: str = ""
    pdf_url: str = ""
    source: str = ""
    extra: dict = field(default_factory=dict)

    def dedup_key(self) -> str:
        if self.doi:
            return self.doi.lower().replace("https://doi.org/", "").strip()
        return f"title::{self.title.lower().strip()}"


class BaseSource:
    name = "base"

    def fetch(self, conf: dict, state: dict) -> List[Paper]:
        raise NotImplementedError

    def _base_paper(self, conf: dict) -> Paper:
        return Paper(
            title="",
            venue_short=conf["short"],
            venue_full=conf["full"],
            ccf_level=conf.get("ccf_level", "A"),
            ccf_category=conf.get("ccf_category", ""),
            source=self.name,
        )

    def _conf_year(self, conf: dict) -> int:
        """会议年份：优先读 yaml，缺省回退当前年。"""
        y = conf.get("conf_year")
        if y:
            return int(y)
        return date.today().year
