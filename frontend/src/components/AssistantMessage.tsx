import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownNode {
  type: string;
  value?: string;
  children?: MarkdownNode[];
  data?: { hProperties?: Record<string, unknown> };
}

function textOf(node: MarkdownNode): string {
  return node.value ?? node.children?.map(textOf).join('') ?? '';
}

/** Preserve content while adapting client tables to a narrow chat panel. */
function remarkChatFormatting() {
  return (tree: MarkdownNode) => {
    function walk(node: MarkdownNode) {
      if (node.type === 'table' && node.children?.length) {
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

export default function AssistantMessage({ content }: { content: string }) {
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
          a: ({ href, children }) => href ? (
            <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
          ) : <span>{children}</span>,
        }}
      >
        {content}
      </Markdown>
    </div>
  );
}
