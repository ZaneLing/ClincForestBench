'use client';

import { useState } from 'react';
import { Copy, Maximize2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { useLanguage } from '@/features/i18n/language-context';

export function JsonView({ value }: { value: unknown }) {
  const { isChinese: zh } = useLanguage();
  const [notice, setNotice] = useState('');
  const text = JSON.stringify(value ?? null, null, 2);
  return (
    <div className="ws-json-view">
      <button
        className="ws-button"
        onClick={() =>
          void navigator.clipboard
            .writeText(text)
            .then(() => setNotice(zh ? '已复制' : 'Copied'))
            .catch(() =>
              setNotice(
                zh
                  ? '复制失败，请手动选择文本'
                  : 'Copy failed. Select the text manually.',
              ),
            )
        }
      >
        <Copy size={13} />
        {notice || (zh ? '复制 JSON' : 'Copy JSON')}
      </button>
      <pre>
        {text.split('\n').map((line, i) => (
          <span className="ws-json-line" key={i}>
            <i aria-hidden="true">{i + 1}</i>
            <code>{line || ' '}</code>
          </span>
        ))}
      </pre>
    </div>
  );
}

export function JsonCell({
  value,
  maxLines = 3,
}: {
  value: unknown;
  maxLines?: number;
}) {
  const [open, setOpen] = useState(false);
  const { isChinese: zh } = useLanguage();
  if (value == null) return <span className="ws-muted">—</span>;
  return (
    <>
      <button
        className="ws-json-cell"
        aria-label={
          zh ? '展开初始信息 JSON' : 'Expand initial information JSON'
        }
        onClick={(e) => {
          e.stopPropagation();
          setOpen(true);
        }}
      >
        <code style={{ WebkitLineClamp: maxLines }}>
          {JSON.stringify(value)}
        </code>
        <Maximize2 size={12} />
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="ws-json-dialog">
          <DialogTitle>{zh ? '初始信息' : 'Initial information'}</DialogTitle>
          <DialogDescription>
            {zh ? '病例源数据' : 'Case source data'}
          </DialogDescription>
          <JsonView value={value} />
        </DialogContent>
      </Dialog>
    </>
  );
}
