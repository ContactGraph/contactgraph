import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { PersonDetailResult } from "@/lib/api-types";
import { formatDate, formatSourceType } from "@/lib/formatters";

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

export function PersonDetailPanel({ person }: { person: PersonDetailResult }) {
  return (
    <div className="flex-1 space-y-6 overflow-y-auto px-6 py-4">
      <div className="space-y-2">
        <div className="flex flex-wrap gap-2">
          {person.is_human ? <Badge variant="success">Human</Badge> : null}
          {person.is_broadcast ? <Badge variant="warning">Broadcast</Badge> : null}
          {person.is_automated ? <Badge variant="secondary">Automated</Badge> : null}
        </div>
        <p className="text-sm text-muted-foreground">{person.message}</p>
      </div>

      <dl className="grid gap-4">
        <DetailField label="First name" value={person.first_name} />
        <DetailField label="Last name" value={person.last_name} />
        <DetailField label="Primary email" value={person.primary_email} />
        <DetailField label="Phone" value={person.phone} />
        <DetailField label="Organization" value={person.org_name} />
        <DetailField label="Role" value={person.current_role} />
        <DetailField label="Location" value={person.location} />
        <DetailField
          label="First contact"
          value={formatDate(person.first_contact_at)}
        />
        <DetailField
          label="Last contact"
          value={formatDate(person.last_contact_at)}
        />
        <DetailField
          label="Last genuine interaction"
          value={formatDate(person.last_genuine_interaction_at)}
        />
        <DetailField
          label="Tie strength"
          value={person.tie_strength_score.toFixed(2)}
        />
        <DetailField
          label="Email count"
          value={person.email_count.toString()}
        />
      </dl>

      {person.emails.length > 0 ? (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Emails</h3>
          <ul className="space-y-1 text-sm">
            {person.emails.map((email: string) => (
              <li key={email}>{email}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {person.sources.length > 0 ? (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Sources</h3>
          <div className="flex flex-wrap gap-2">
            {person.sources.map((source: string) => (
              <Badge key={source} variant="outline">
                {formatSourceType(source)}
              </Badge>
            ))}
          </div>
        </section>
      ) : null}

      {Object.keys(person.social_profiles).length > 0 ? (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Web links</h3>
          <ul className="space-y-2 text-sm">
            {Object.entries(person.social_profiles).map(([platform, url]) => (
              <li key={platform}>
                <span className="font-medium capitalize">{platform}: </span>
                <a
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary underline-offset-4 hover:underline"
                >
                  {url}
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {person.inferred_categories.length > 0 ? (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Categories</h3>
          <div className="flex flex-wrap gap-2">
            {person.inferred_categories.map((category: string) => (
              <Badge key={category} variant="secondary">
                {category}
              </Badge>
            ))}
          </div>
        </section>
      ) : null}

      {person.bio_summary ? (
        <>
          <Separator />
          <section className="space-y-2">
            <h3 className="text-sm font-medium">Bio</h3>
            <p className="text-sm text-muted-foreground">{person.bio_summary}</p>
          </section>
        </>
      ) : null}
    </div>
  );
}
