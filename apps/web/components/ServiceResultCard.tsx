import Link from "next/link";
import { ProfileMedia } from "@/components/ProfileMedia";
import { categoryLabel } from "@/lib/copy";
import { money } from "@/lib/format";

export type PublicServiceItem = {
  id: string;
  title: string;
  description?: string;
  city: string;
  category_code: string;
  honorarium_rub?: number | null;
  profile_name?: string | null;
  profile_verified?: boolean;
  media_url?: string | null;
  profile_href?: string | null;
  resource_type?: string | null;
  resource_id?: string | null;
};

type ServiceResultCardProps = {
  item: PublicServiceItem;
  querySuffix?: string;
};

export function ServiceResultCard({ item, querySuffix }: ServiceResultCardProps) {
  const hrefBase =
    item.profile_href ||
    (item.resource_type === "venue" && item.resource_id
      ? `/venues/${item.resource_id}`
      : item.resource_type === "artist" && item.resource_id
        ? `/artists/${item.resource_id}`
        : "/search?kind=artist");
  const href = querySuffix ? `${hrefBase}?${querySuffix}` : hrefBase;
  const name = item.profile_name || item.title;

  return (
    <article className="card catalog-result catalog-result--service" data-testid="service-result-card">
      <div className="catalog-card-media">
        <Link className="catalog-image-link" href={href} aria-label={`Открыть профиль: ${name}`}>
          <ProfileMedia src={item.media_url} name={name} compact />
        </Link>
        <span className="catalog-availability chip ok">Услуга</span>
      </div>
      <div className="catalog-card-content">
        <div className="card-head">
          <Link href={href}>
            <strong>{item.title}</strong>
          </Link>
          {item.profile_verified ? (
            <span className="catalog-verified-mark" role="img" aria-label="Профиль подтверждён" title="Профиль подтверждён">
              ✓
            </span>
          ) : null}
        </div>
        <p className="catalog-card-location">
          {categoryLabel(item.category_code)} <span aria-hidden="true">·</span> {item.city}
          {item.profile_name ? (
            <>
              {" "}
              <span aria-hidden="true">·</span> {item.profile_name}
            </>
          ) : null}
        </p>
        {item.description ? <p className="catalog-card-address">{item.description}</p> : null}
        <div className="catalog-card-footer">
          <p className="catalog-price">
            {item.honorarium_rub != null && item.honorarium_rub > 0 ? (
              <>
                <span>Ориентир</span>
                {money(item.honorarium_rub)}
              </>
            ) : (
              <span className="catalog-price-request">Цена по запросу</span>
            )}
          </p>
          <Link className="btn secondary catalog-open" href={href}>
            К исполнителю <span aria-hidden="true">↗</span>
          </Link>
        </div>
      </div>
    </article>
  );
}
