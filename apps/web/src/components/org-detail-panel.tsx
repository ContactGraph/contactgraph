import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { OrgDetailResult } from "@/lib/api-types";

function DetailField({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  if (!value) {
    return null;
  }
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-1 text-sm">{value}</dd>
    </div>
  );
}

function DetailLinkField({
  label,
  href,
}: {
  label: string;
  href: string | null | undefined;
}) {
  if (!href) {
    return null;
  }
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-1 text-sm">
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          className="text-primary underline-offset-2 hover:underline"
        >
          {href}
        </a>
      </dd>
    </div>
  );
}

export function OrgDetailPanel({ org }: { org: OrgDetailResult }) {
  return (
    <div className="flex-1 space-y-6 overflow-y-auto px-6 py-4">
      <p className="text-sm text-muted-foreground">{org.message}</p>

      <dl className="grid gap-4">
        <DetailField label="Name" value={org.name} />
        <DetailField label="Domain" value={org.primary_domain} />
        <DetailField label="Description" value={org.description} />
        <DetailLinkField
          label="Website"
          href={org.primary_domain ? `https://${org.primary_domain}` : null}
        />
        <DetailLinkField label="LinkedIn" href={org.linkedin_url} />
        <DetailLinkField label="Careers" href={org.careers_url} />
        <DetailField
          label="Contacts"
          value={org.contact_count.toString()}
        />
      </dl>

      {org.categories.length > 0 ? (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Categories</h3>
          <div className="flex flex-wrap gap-2">
            {org.categories.map((category: string) => (
              <Badge key={category} variant="secondary">
                {category}
              </Badge>
            ))}
          </div>
        </section>
      ) : null}

      {org.aliases.length > 0 ? (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Aliases</h3>
          <ul className="space-y-1 text-sm">
            {org.aliases.map((alias: string) => (
              <li key={alias}>{alias}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <Separator />

      <section className="space-y-3">
        <h3 className="text-sm font-medium">People at this organization</h3>
        {org.people.length === 0 ? (
          <p className="text-sm text-muted-foreground">No contacts linked yet.</p>
        ) : (
          <ul className="divide-y rounded-md border">
            {org.people.map((person) => (
              <li key={person.person_id} className="px-3 py-2 text-sm">
                <p className="font-medium">{person.display_name}</p>
                <p className="text-muted-foreground">
                  {[person.current_role, person.primary_email]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
