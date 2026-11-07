import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useEffect, useRef, useState } from 'react';
import { downloadCampaignTable } from '../lib/campaignExport';
import { downloadRecommendationList } from '../lib/recommendationExport';
import { getRecommendationList } from '../services/chatApi';

interface MarkdownNode {
  type: string;
  value?: string;
  url?: string;
  children?: MarkdownNode[];
  data?: { hProperties?: Record<string, unknown> };
}

function textOf(node: MarkdownNode): string {
  return node.value ?? node.children?.map(textOf).join('') ?? '';
}

/** Preserve content while adapting client tables to a narrow chat panel. */
function remarkChatFormatting() {
  return (tree: MarkdownNode) => {
    let latestTable: string[][] | undefined;
    function walk(node: MarkdownNode) {
      if (node.type === 'table' && node.children?.length) {
        latestTable = node.children.map((row) => row.children?.map(textOf) ?? []);
        const headers = node.children[0].children?.map(textOf) ?? [];
        const keys = headers.map((header) => header.toLowerCase().replace(/[^a-z]/g, ''));
        const clientTable = headers.length === 3
          && ['contactid', 'clientid'].includes(keys[0])
          && ['clientname', 'name'].includes(keys[1]);
        if (clientTable) {
          node.data = { ...node.data, hProperties: { ...node.data?.hProperties, 'data-client-cards': true } };
          for (const row of node.children.slice(1)) {
            row.children?.forEach((cell, index) => {
              cell.data = { ...cell.data, hProperties: {
                ...cell.data?.hProperties, 'data-label': headers[index], 'data-column': index,
              } };
            });
          }
        }
      }
      if (node.type === 'link' && node.url === '#active-campaigns-excel' && latestTable) {
        node.data = { ...node.data, hProperties: {
          ...node.data?.hProperties, 'data-campaign-export': JSON.stringify(latestTable),
        } };
      }
      node.children?.forEach((child, index) => {
        // Only recognize a line break; never enable arbitrary model-generated HTML.
        // Working on the parsed tree leaves <br> inside code examples untouched.
        if (child.type === 'html' && /^<br\s*\/?\s*>$/i.test(child.value ?? '')) {
          node.children![index] = { type: 'break' };
        } else {
          walk(child);
        }
      });
    }
    walk(tree);
  };
}

function CampaignExcelLink({ table }: { table: string[][] }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  return (
    <>
      <a
        href="#active-campaigns-excel"
        aria-disabled={busy}
        onClick={async (event) => {
          event.preventDefault();
          if (busy) return;
          setBusy(true);
          setError(false);
          try {
            await downloadCampaignTable(table);
          } catch {
            setError(true);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? 'Preparing Excel…' : 'Download Excel (.xlsx)'}
      </a>
      {error && <span role="alert"> Unable to download Excel. Please try again.</span>}
    </>
  );
}

function RecommendationExcelLink({ listId, advisorId }: { listId: string; advisorId: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => { request.current?.abort(); }, [advisorId, listId]);
  return <>
    <a href={`#recommendation-excel-${listId}`} aria-disabled={busy} onClick={async (event) => {
      event.preventDefault();
      if (busy) return;
      const controller = new AbortController();
      request.current = controller;
      setBusy(true);
      setError('');
      try {
        const result = await getRecommendationList(listId, advisorId, controller.signal);
        if (!controller.signal.aborted) downloadRecommendationList(result);
      } catch (cause) {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Unable to download. Please retry.');
      } finally {
        if (!controller.signal.aborted) setBusy(false);
      }
    }}>{busy ? 'Preparing Excel…' : 'Download full results (.xlsx)'}</a>
    {error && <span role="alert"> {error}</span>}
  </>;
}

export default function AssistantMessage({ content, advisorId }: { content: string; advisorId?: string }) {
  return (
    <div className="pulse-markdown">
      <Markdown
        remarkPlugins={[remarkGfm, remarkChatFormatting]}
        skipHtml
        allowedElements={[
          'p', 'strong', 'em', 'del', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
          'ul', 'ol', 'li', 'blockquote', 'hr', 'br', 'code', 'pre', 'a',
          'table', 'thead', 'tbody', 'tr', 'th', 'td', 'input',
        ]}
        components={{
          table: ({ node, children }) => (
            <div className="pulse-table-wrap">
              <table className={node?.properties['data-client-cards'] ? 'pulse-client-cards' : undefined}>
                {children}
              </table>
            </div>
          ),
          td: ({ node, children, ...props }) => (
            <td {...props}>
              {node?.properties['data-label'] && (
                <span className="pulse-cell-label">{String(node.properties['data-label'])}</span>
              )}
              {children}
            </td>
          ),
          a: ({ node, href, children }) => {
            const recommendation = href?.match(/^#recommendation-excel-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i);
            if (recommendation) return advisorId
              ? <RecommendationExcelLink key={`${advisorId}:${recommendation[1]}`} listId={recommendation[1]} advisorId={advisorId} />
              : <span>Sign in as an adviser to download these results.</span>;
            const snapshot = node?.properties['data-campaign-export'];
            if (href === '#active-campaigns-excel' && typeof snapshot === 'string') {
              return <CampaignExcelLink table={JSON.parse(snapshot) as string[][]} />;
            }
            if (href === '#active-campaigns-excel') return <span>Excel download unavailable</span>;
            return href ? (
              <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
            ) : <span>{children}</span>;
          },
        }}
      >
        {content}
      </Markdown>
    </div>
  );
}
