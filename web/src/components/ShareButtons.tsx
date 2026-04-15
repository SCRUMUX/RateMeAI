import { useState } from 'react';

interface Props {
  url: string;
  text: string;
  imageUrl?: string;
  compact?: boolean;
}

function enc(s: string) {
  return encodeURIComponent(s);
}

function buildPlatforms(imageUrl?: string) {
  return [
    {
      id: 'vk' as const,
      label: 'VK',
      getUrl: (url: string, text: string) => {
        let shareUrl = `https://vk.com/share.php?url=${enc(url)}&title=${enc(text)}`;
        if (imageUrl) shareUrl += `&image=${enc(imageUrl)}`;
        return shareUrl;
      },
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <path d="M21.547 7h-3.29a.743.743 0 0 0-.655.392s-1.312 2.416-1.734 3.23C14.734 12.813 14 12.126 14 11.11V7.603A1.104 1.104 0 0 0 12.896 6.5h-2.474a1.982 1.982 0 0 0-1.75.813s1.255-.204 1.255 1.49c0 .42.022 1.626.04 2.64a.73.73 0 0 1-1.272.503 21.54 21.54 0 0 1-2.498-4.543.693.693 0 0 0-.63-.403H2.453a.5.5 0 0 0-.472.667c1.32 3.916 6.147 8.263 10.656 8.263h1.49a.742.742 0 0 0 .742-.742v-1.296c-.01-.424.27-.634.61-.522.54.176 1.522 1.09 2.273 1.96a1.006 1.006 0 0 0 .758.35h2.86a.5.5 0 0 0 .416-.776c-.974-1.474-2.128-2.7-2.462-3.13-.33-.43-.244-.62 0-1.004.246-.384 2.607-3.617 2.607-3.617A.5.5 0 0 0 21.547 7z"/>
        </svg>
      ),
    },
    {
      id: 'ok' as const,
      label: 'OK',
      getUrl: (url: string, text: string) => {
        let shareUrl = `https://connect.ok.ru/offer?url=${enc(url)}&title=${enc(text)}`;
        if (imageUrl) shareUrl += `&imageUrl=${enc(imageUrl)}`;
        return shareUrl;
      },
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9zm0 2.4a2.1 2.1 0 1 0 0 4.2 2.1 2.1 0 0 0 0-4.2zm3.31 8.12a6.58 6.58 0 0 1-3.31.88 6.58 6.58 0 0 1-3.31-.88 1.2 1.2 0 0 0-1.22 2.06A8.9 8.9 0 0 0 10.5 16l-2.78 2.78a1.2 1.2 0 0 0 1.7 1.7L12 17.88l2.59 2.59a1.2 1.2 0 0 0 1.7-1.7L13.5 16a8.9 8.9 0 0 0 3.03-1.42 1.2 1.2 0 0 0-1.22-2.06z"/>
        </svg>
      ),
    },
    {
      id: 'telegram' as const,
      label: 'Telegram',
      getUrl: (url: string, text: string) => {
        const shareLink = imageUrl || url;
        return `https://t.me/share/url?url=${enc(shareLink)}&text=${enc(text)}`;
      },
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>
        </svg>
      ),
    },
    {
      id: 'whatsapp' as const,
      label: 'WhatsApp',
      getUrl: (url: string, text: string) => {
        const link = imageUrl || url;
        return `https://wa.me/?text=${enc(text + ' ' + link)}`;
      },
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 0 0-3.48-8.413z"/>
        </svg>
      ),
    },
    {
      id: 'instagram' as const,
      label: 'Instagram',
      getUrl: null as null,
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 1 0 0 12.324 6.162 6.162 0 0 0 0-12.324zM12 16a4 4 0 1 1 0-8 4 4 0 0 1 0 8zm6.406-11.845a1.44 1.44 0 1 0 0 2.881 1.44 1.44 0 0 0 0-2.881z"/>
        </svg>
      ),
    },
  ];
}

export default function ShareButtons({ url, text, imageUrl, compact }: Props) {
  const [copied, setCopied] = useState(false);
  const platforms = buildPlatforms(imageUrl);

  async function handleClick(platform: ReturnType<typeof buildPlatforms>[number]) {
    if (platform.getUrl) {
      window.open(platform.getUrl(url, text), '_blank', 'noopener,noreferrer');
    } else {
      const copyTarget = imageUrl || url;
      try {
        await navigator.clipboard.writeText(copyTarget);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch { /* clipboard not available */ }
    }
  }

  const btnSize = compact ? 'w-9 h-9' : 'w-10 h-10';

  return (
    <div className="flex flex-col gap-[var(--space-6)]">
      {!compact && (
        <span className="text-[13px] leading-[18px] text-[var(--color-text-muted)] text-center">Поделиться</span>
      )}
      <div className="flex items-center justify-center gap-[var(--space-8)]">
        {platforms.map((p) => (
          <button
            key={p.id}
            onClick={() => handleClick(p)}
            title={p.id === 'instagram' ? (copied ? 'Скопировано!' : 'Скопировать ссылку') : p.label}
            className={`${btnSize} rounded-full flex items-center justify-center text-[#E6EEF8] transition-all hover:scale-110 cursor-pointer`}
            style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.10)' }}
          >
            {p.icon}
          </button>
        ))}
      </div>
      {copied && (
        <span className="text-[12px] leading-[16px] text-[var(--color-success-base)] text-center">
          Ссылка скопирована! Вставьте в Instagram
        </span>
      )}
    </div>
  );
}
