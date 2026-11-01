"use client";

import { useEffect, useRef, useSyncExternalStore } from "react";
import type { Citation, DocumentInfo } from "../lib/api";
import { Modal } from "./ui/Modal";
import styles from "./SourceInspector.module.css";

export interface SourceInspectorProps {
  open: boolean;
  mobileOpen: boolean;
  sources: Citation[];
  documents: DocumentInfo[];
  document: DocumentInfo | null;
  selectedChunkId: string | null;
  onClose: () => void;
  onSelect: (citation: Citation) => void;
  onOpenDocument: (documentId: string, pageNumber?: number | null) => void;
  streaming?: boolean;
}

const DESKTOP_QUERY = "(min-width: 1280px)";

function subscribeDesktop(onChange: () => void) {
  const query = window.matchMedia(DESKTOP_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

const getDesktopSnapshot = () => window.matchMedia(DESKTOP_QUERY).matches;
const getServerSnapshot = () => false;

function scrollToCard(card: HTMLElement) {
  const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
  card.scrollIntoView({ behavior, block: "nearest" });
}

function validPage(value: number | null | undefined) {
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : null;
}

function formatSize(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return null;
  if (value < 1024) return `${Math.round(value)} B`;
  const units = ["KB", "MB", "GB", "TB", "PB"];
  let size = value / 1024;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size < 10 ? size.toFixed(1) : Math.round(size)} ${units[unit]}`;
}

function formatStatus(value: string) {
  const status = value.trim().replace(/[_-]+/g, " ");
  return status ? status.replace(/\b\w/g, (letter) => letter.toUpperCase()) : "Unavailable";
}

interface PassageProps {
  citation: Citation;
  index: number;
  filename: string;
  selected: boolean;
  onSelect: (citation: Citation) => void;
  onOpenDocument: SourceInspectorProps["onOpenDocument"];
  registerCard: (chunkId: string, card: HTMLElement | null) => void;
}

function SourcePassage({
  citation, index, filename, selected, onSelect, onOpenDocument, registerCard,
}: PassageProps) {
  const page = validPage(citation.page_number);
  return (
    <li className={styles.listItem}>
      <article
        ref={(card) => registerCard(citation.chunk_id, card)}
        className={`${styles.passage} ${selected ? styles.passageSelected : ""}`}
        tabIndex={-1}
        aria-label={`Passage ${index + 1} from ${filename}`}
        aria-current={selected ? "location" : undefined}
      >
        <div className={styles.passageHeader}>
          <button
            className={`index-label ${styles.indexButton}`}
            type="button"
            aria-label={`${selected ? "Selected" : "Select"} passage ${index + 1}`}
            aria-pressed={selected}
            onClick={() => onSelect(citation)}
          >[{index + 1}]</button>
          <div className={styles.sourceIdentity}>
            <span className={styles.filename}>{filename}</span>
            {page !== null && <span className={styles.pageLabel}>Page {page}</span>}
          </div>
          <button
            className={styles.openButton}
            type="button"
            disabled={!citation.document_id}
            onClick={() => onOpenDocument(citation.document_id, page)}
          >
            {page === null ? "Open document" : `View page ${page}`}<span aria-hidden="true"> ↗</span>
          </button>
        </div>
        <p className={styles.excerpt}>
          {citation.excerpt.trim() ? citation.excerpt : "No excerpt available."}
        </p>
        <details className={styles.retrievalDetails}>
          <summary>Retrieval details</summary>
          <dl className={styles.detailList}>
            {Number.isFinite(citation.score) && <div><dt>Relevance score</dt><dd>{citation.score.toFixed(3)}</dd></div>}
            <div><dt>Chunk ID</dt><dd className={styles.detailValue}>{citation.chunk_id}</dd></div>
            <div><dt>Document ID</dt><dd className={styles.detailValue}>{citation.document_id}</dd></div>
          </dl>
        </details>
      </article>
    </li>
  );
}

function EmptyState({ document, streaming }: { document: DocumentInfo | null; streaming: boolean }) {
  const pages = document?.page_count;
  const pageCount = typeof pages === "number" && Number.isInteger(pages) && pages >= 0
    ? `${pages} ${pages === 1 ? "page" : "pages"}`
    : "Unavailable";

  return (
    <section className={styles.emptyState}>
      {document ? (
        <>
          <p className={styles.eyebrow}>Current document</p>
          <h3 className={styles.documentTitle}>{document.filename.trim() || "Document details unavailable"}</h3>
          <dl className={styles.documentFacts}>
            <div><dt>Type</dt><dd>{document.mime_type.trim() || "Unavailable"}</dd></div>
            <div><dt>Pages</dt><dd>{pageCount}</dd></div>
            <div><dt>Size</dt><dd>{formatSize(document.file_size) ?? "Unavailable"}</dd></div>
            <div><dt>Status</dt><dd>{formatStatus(document.status)}</dd></div>
          </dl>
        </>
      ) : <p className={styles.emptyTitle}>No current document</p>}
      <p className={styles.emptyNote} aria-live="polite">
        {streaming
          ? "The answer is still streaming. Citations will appear here when available."
          : "Citations appear here after an answer includes source passages."}
      </p>
    </section>
  );
}

export default function SourceInspector({
  open, mobileOpen, sources, documents, document, selectedChunkId,
  onClose, onSelect, onOpenDocument, streaming = false,
}: SourceInspectorProps) {
  const isDesktop = useSyncExternalStore(subscribeDesktop, getDesktopSnapshot, getServerSnapshot);
  const cards = useRef(new Map<string, HTMLElement>());
  const passageCount = `${sources.length} ${sources.length === 1 ? "passage" : "passages"}`;

  useEffect(() => {
    if (!selectedChunkId) return;
    const card = cards.current.get(selectedChunkId);
    if (card) scrollToCard(card);
  }, [isDesktop, mobileOpen, selectedChunkId, sources]);

  const registerCard = (chunkId: string, card: HTMLElement | null) => {
    if (card) cards.current.set(chunkId, card);
    else cards.current.delete(chunkId);
  };
  const selectCitation = (citation: Citation) => {
    onSelect(citation);
    const card = cards.current.get(citation.chunk_id);
    if (card) {
      card.focus({ preventScroll: true });
      scrollToCard(card);
    }
  };

  const panel = (
    <div className={`${styles.panel} ${isDesktop ? "" : styles.mobilePanel}`}>
      {isDesktop && (
        <header className={styles.header}>
          <div><p className={styles.eyebrow}>From this answer</p><h2 className={`editorial-heading ${styles.title}`}>Sources</h2></div>
          <div className={styles.headerActions}>
            <span className={styles.count} aria-live="polite">{passageCount}</span>
            <button className={styles.closeButton} type="button" onClick={onClose} aria-label="Close sources">×</button>
          </div>
        </header>
      )}
      {sources.length > 0 && <p className={styles.helper}>Passages used in the latest answer.</p>}
      <div className={styles.body}>
        {sources.length > 0 ? (
          <ol className={styles.sourceList} aria-label="Cited source passages">
            {sources.map((citation, index) => {
              const filename = documents.find((item) => item.id === citation.document_id)?.filename.trim()
                || "Document details unavailable";
              return (
                <SourcePassage
                  key={`${citation.chunk_id}:${index}`}
                  citation={citation}
                  index={index}
                  filename={filename}
                  selected={selectedChunkId === citation.chunk_id}
                  onSelect={selectCitation}
                  onOpenDocument={onOpenDocument}
                  registerCard={registerCard}
                />
              );
            })}
          </ol>
        ) : <EmptyState document={document} streaming={streaming} />}
      </div>
    </div>
  );

  if (isDesktop) {
    return open ? <aside className={styles.rail} aria-label="Sources">{panel}</aside> : null;
  }
  return (
    <Modal open={mobileOpen} onClose={onClose} title={`Sources (${passageCount})`} width={420} className={styles.mobileModal}>
      {panel}
    </Modal>
  );
}
