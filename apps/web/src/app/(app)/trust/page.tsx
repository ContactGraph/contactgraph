"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Children, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  EditTrustedUsersResult,
  ViewTrustedUsersResult,
} from "@/lib/api-types";
import { formatDate } from "@/lib/formatters";
import { proxyPost } from "@/lib/proxy-client";

export default function TrustPage() {
  const queryClient = useQueryClient();
  const [inviteEmail, setInviteEmail] = useState<string>("");
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [inviteCopy, setInviteCopy] = useState<string | null>(null);

  const trustQuery = useQuery({
    queryKey: ["trust-list"],
    queryFn: () => proxyPost<ViewTrustedUsersResult>("view-trusted-users"),
  });

  const editMutation = useMutation({
    mutationFn: (body: Record<string, string[] | undefined>) =>
      proxyPost<EditTrustedUsersResult>("edit-trusted-users", body),
    onSuccess: async (result: EditTrustedUsersResult) => {
      setActionMessage(result.message);
      if (result.invite_copy) {
        setInviteCopy(result.invite_copy);
      }
      await queryClient.invalidateQueries({ queryKey: ["trust-list"] });
    },
    onError: (error: Error) => {
      setActionMessage(error.message);
    },
  });

  const data: ViewTrustedUsersResult | undefined = trustQuery.data;

  const handleInvite = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const email: string = inviteEmail.trim();
    if (!email) {
      return;
    }
    editMutation.mutate({ add: [email] });
    setInviteEmail("");
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Trust List</h1>
        <p className="text-muted-foreground">
          Share second-degree network access with people you trust (max{" "}
          {data?.max_members ?? 20} members).
        </p>
      </div>

      {actionMessage ? (
        <Alert>
          <AlertDescription>{actionMessage}</AlertDescription>
        </Alert>
      ) : null}

      {inviteCopy ? (
        <Alert>
          <AlertTitle>Invite message</AlertTitle>
          <AlertDescription className="whitespace-pre-wrap">
            {inviteCopy}
          </AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Invite someone</CardTitle>
          <CardDescription>
            Send a trust-list invite by email address.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-col gap-3 sm:flex-row sm:items-end"
            onSubmit={handleInvite}
          >
            <div className="flex-1 space-y-2">
              <Label htmlFor="invite-email">Email</Label>
              <Input
                id="invite-email"
                type="email"
                value={inviteEmail}
                onChange={(event) => setInviteEmail(event.target.value)}
                placeholder="friend@example.com"
              />
            </div>
            <Button type="submit" disabled={editMutation.isPending}>
              Send invite
            </Button>
          </form>
        </CardContent>
      </Card>

      {trustQuery.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <TrustSection
            title="Members"
            description={`${data?.members.length ?? 0} active`}
            empty="No trust-list members yet."
          >
            {data?.members.map((member) => (
              <li
                key={member.membership_id}
                className="flex items-center justify-between gap-3 py-3"
              >
                <div>
                  <p className="font-medium">
                    {member.name ?? member.email}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {member.email} · since {formatDate(member.established_at)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">{member.status}</Badge>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      editMutation.mutate({ remove: [member.email] })
                    }
                    disabled={editMutation.isPending}
                  >
                    Remove
                  </Button>
                </div>
              </li>
            ))}
          </TrustSection>

          <TrustSection
            title="Inbound invites"
            description="Requests waiting for your response"
            empty="No pending inbound invites."
          >
            {data?.inbound_invites.map((invite) => (
              <li
                key={invite.invite_id}
                className="flex items-center justify-between gap-3 py-3"
              >
                <div>
                  <p className="font-medium">
                    {invite.inviter_name ?? invite.inviter_email}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {invite.inviter_email} · {formatDate(invite.created_at)}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={() =>
                      editMutation.mutate({ accept: [invite.inviter_email] })
                    }
                    disabled={editMutation.isPending}
                  >
                    Accept
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      editMutation.mutate({ decline: [invite.inviter_email] })
                    }
                    disabled={editMutation.isPending}
                  >
                    Decline
                  </Button>
                </div>
              </li>
            ))}
          </TrustSection>

          <TrustSection
            title="Outbound invites"
            description="Invites you have sent"
            empty="No outbound invites."
            className="lg:col-span-2"
          >
            {data?.outbound_invites.map((invite) => (
              <li
                key={invite.invite_id}
                className="flex items-center justify-between gap-3 py-3"
              >
                <div>
                  <p className="font-medium">{invite.invitee_email}</p>
                  <p className="text-sm text-muted-foreground">
                    Sent {formatDate(invite.created_at)}
                  </p>
                </div>
                <Badge variant="outline">{invite.status}</Badge>
              </li>
            ))}
          </TrustSection>
        </div>
      )}
    </div>
  );
}

function TrustSection({
  title,
  description,
  empty,
  className,
  children,
}: {
  title: string;
  description: string;
  empty: string;
  className?: string;
  children: React.ReactNode;
}) {
  const hasItems: boolean = Children.count(children) > 0;

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {hasItems ? (
          <ul className="divide-y">{children}</ul>
        ) : (
          <p className="text-sm text-muted-foreground">{empty}</p>
        )}
      </CardContent>
    </Card>
  );
}
