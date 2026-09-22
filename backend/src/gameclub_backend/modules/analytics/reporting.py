from __future__ import annotations

import asyncio
import csv
import datetime
import enum
import hashlib
import io
import secrets
import typing
import uuid
import zipfile
from dataclasses import dataclass, replace
from xml.sax.saxutils import escape


class ExportFormat(enum.StrEnum):
    CSV = "csv"
    XLSX = "xlsx"
    PDF = "pdf"


class ReportStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NOT_AVAILABLE = "not_available"
    CANCELLED = "cancelled"


class ReportPermissionError(PermissionError):
    pass


class ReportFormatUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ReportJob:
    id: uuid.UUID
    requested_by: str
    report_name: str
    export_format: ExportFormat
    idempotency_key: str
    include_pii: bool
    timeout_seconds: int
    max_attempts: int
    status: ReportStatus = ReportStatus.PENDING
    attempts: int = 0
    created_at: datetime.datetime = datetime.datetime.min.replace(tzinfo=datetime.UTC)
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None
    error: str | None = None
    artifact_token: str | None = None
    artifact_content_type: str | None = None
    artifact_sha256: str | None = None
    artifact_size: int | None = None


class ReportJobRepository(typing.Protocol):
    async def create_report_job(self, job: ReportJob) -> ReportJob: ...

    async def get_report_job(self, job_id: uuid.UUID) -> ReportJob: ...

    async def update_report_job(self, job: ReportJob) -> ReportJob: ...

    async def store_artifact(
        self, job: ReportJob, content: bytes, content_type: str
    ) -> ReportJob: ...

    async def read_artifact(self, job: ReportJob, token: str) -> tuple[bytes, str, str, int]: ...


@dataclass(frozen=True, slots=True)
class ReportArtifact:
    content: bytes
    content_type: str
    sha256: str
    size: int


def _safe_csv_value(value: object) -> str:
    text = str(value)
    return "'" + text if text[:1] in {"=", "+", "-", "@"} else text


def render_report(
    export_format: ExportFormat, rows: typing.Iterable[dict[str, object]]
) -> tuple[bytes, str]:
    rows_list = list(rows)
    keys = sorted({key for row in rows_list for key in row})
    if export_format is ExportFormat.XLSX:
        return _render_xlsx(keys, rows_list), (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    if export_format is ExportFormat.PDF:
        return _render_pdf(keys, rows_list), "application/pdf"
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=keys, lineterminator="\n")
    writer.writeheader()
    for row in rows_list:
        writer.writerow({key: _safe_csv_value(row.get(key, "")) for key in keys})
    return output.getvalue().encode("utf-8"), "text/csv; charset=utf-8"


def _render_xlsx(keys: list[str], rows: list[dict[str, object]]) -> bytes:
    values = [keys] + [[str(row.get(key, "")) for key in keys] for row in rows]
    sheet_rows: list[str] = []
    for row_number, values_row in enumerate(values, start=1):
        cells = []
        for column_number, value in enumerate(values_row, start=1):
            reference = f"{_column_name(column_number)}{row_number}"
            cells.append(
                f'<c r="{reference}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
            )
        sheet_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(sheet_rows)}</sheetData></worksheet>"
    )
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-'
            'package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-'
            'officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Analytics" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        ),
        "xl/worksheets/sheet1.xml": sheet,
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def _render_pdf(keys: list[str], rows: list[dict[str, object]]) -> bytes:
    lines = [" | ".join(keys)]
    lines.extend(" | ".join(str(row.get(key, "")) for key in keys) for row in rows)
    commands = ["BT", "/F1 9 Tf", "36 756 Td"]
    for index, line in enumerate(lines[:55]):
        if index:
            commands.append("0 -12 Td")
        safe = line.encode("latin-1", errors="replace").decode("latin-1")
        safe = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"({safe}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    output = io.BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for number, content in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{number} 0 obj\n".encode())
        output.write(content)
        output.write(b"\nendobj\n")
    xref_offset = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode())
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return output.getvalue()


def _column_name(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


class ReportJobService:
    def __init__(self, repository: ReportJobRepository) -> None:
        self._repository = repository

    async def create_job(
        self,
        *,
        requested_by: str,
        permissions: typing.Collection[str],
        report_name: str,
        export_format: ExportFormat,
        idempotency_key: str,
        include_pii: bool,
        timeout_seconds: int = 300,
        max_attempts: int = 3,
    ) -> ReportJob:
        granted = set(permissions)
        if "analytics.read" not in granted or "analytics.export" not in granted:
            raise ReportPermissionError(
                "analytics.read and analytics.export permissions are required"
            )
        if include_pii and "analytics.pii" not in granted:
            raise ReportPermissionError("analytics.pii permission is required for PII exports")
        if timeout_seconds <= 0 or max_attempts <= 0:
            raise ValueError("Report timeout and max attempts must be positive")
        job = ReportJob(
            id=uuid.uuid4(),
            requested_by=requested_by,
            report_name=report_name,
            export_format=export_format,
            idempotency_key=idempotency_key,
            include_pii=include_pii,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
            status=ReportStatus.PENDING,
            created_at=datetime.datetime.now(datetime.UTC),
            artifact_token=secrets.token_urlsafe(32),
        )
        return await self._repository.create_report_job(job)

    async def get(self, job_id: uuid.UUID) -> ReportJob:
        return await self._repository.get_report_job(job_id)

    async def complete_job(self, job_id: uuid.UUID, content: bytes, content_type: str) -> ReportJob:
        job = await self.get(job_id)
        return await self._repository.store_artifact(job, content, content_type)

    async def run(
        self,
        job_id: uuid.UUID,
        renderer: typing.Callable[[], typing.Awaitable[tuple[bytes, str]]],
    ) -> ReportStatus:
        job = await self.get(job_id)
        if job.status in {
            ReportStatus.SUCCEEDED,
            ReportStatus.NOT_AVAILABLE,
            ReportStatus.CANCELLED,
        }:
            return job.status
        now = datetime.datetime.now(datetime.UTC)
        running = replace(
            job, status=ReportStatus.RUNNING, attempts=job.attempts + 1, started_at=now
        )
        await self._repository.update_report_job(running)
        try:
            content, content_type = await asyncio.wait_for(renderer(), timeout=job.timeout_seconds)
        except ReportFormatUnavailable as error:
            await self._repository.update_report_job(
                replace(
                    running, status=ReportStatus.NOT_AVAILABLE, error=str(error), completed_at=now
                )
            )
            return ReportStatus.NOT_AVAILABLE
        except Exception as error:
            next_status = (
                ReportStatus.PENDING
                if running.attempts < running.max_attempts
                else ReportStatus.FAILED
            )
            await self._repository.update_report_job(
                replace(running, status=next_status, error=str(error), completed_at=now)
            )
            return next_status
        await self._repository.store_artifact(running, content, content_type)
        return ReportStatus.SUCCEEDED

    async def read_artifact(
        self,
        job_id: uuid.UUID,
        token: str,
        permissions: typing.Collection[str],
    ) -> ReportArtifact:
        if "analytics.read" not in set(permissions):
            raise ReportPermissionError("analytics.read permission is required")
        job = await self.get(job_id)
        if job.status is not ReportStatus.SUCCEEDED:
            raise ReportPermissionError("Artifact is not available")
        try:
            content, content_type, sha256, size = await self._repository.read_artifact(job, token)
        except PermissionError as error:
            raise ReportPermissionError(str(error)) from error
        return ReportArtifact(
            content, content_type, sha256 or hashlib.sha256(content).hexdigest(), size
        )
