# Unraid template

`franchisarr.xml` is a Community Applications template. Until it is in the CA feed, install it by
hand: **Docker → Add Container → Template repositories**, add

    https://github.com/prophetizer/franchisarr/tree/master/contrib/unraid

then pick *franchisarr* from the template dropdown. The config folder defaults to
`/mnt/user/appdata/franchisarr`; PUID/PGID default to Unraid's `nobody:users` (99:100).

## Submitting to Community Applications

CA takes templates from a repository listed in its application feed. Per
[the CA application policies thread](https://forums.unraid.net/topic/87144-ca-application-policies-privacy-policy/):

1. Create a public GitHub repo (e.g. `unraid-templates`) containing this XML, and change
   `TemplateURL` in it to that repo's raw URL. **Never rename or transfer that repo afterwards** —
   the feed's checks treat that as a compromise and blacklist the author's templates.
2. Fill in the [new-repository form](https://form.asana.com/?k=qtIUrf5ydiXvXzPI57BiJw&d=714739274360802)
   linked from that thread (since June 2025 the process is the form, not a forum PM). The
   moderators add the repo; the app then appears in the Apps tab.
3. A support thread in the [Docker Containers forum](https://forums.unraid.net/forum/47-docker-containers/)
   is customary; put its URL in `<Support>` once it exists.
