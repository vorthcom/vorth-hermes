# vorth — Hermes sentinel plugin (beta)

The Vorth Terse beta surface for Hermes agents: free inference on
`beta-deepseek-v4-flash-0731` (262K context), with the sentinel loop —
the server's own junk detectors running client-side, shipping
replayable forensic capsules home. Sensor, not censor: the plugin
observes and reports; filtering stays server-side where it is
certified.

Install:

    hermes plugins install <this-repo-url>

Then see `after-install.md` (shown automatically on install).

Versioned detectors: `vorth_filters/` is vendored verbatim from the
server; a capsule is admitted only if the server can replay the same
versioned detector against the capsule's own payload and reproduce the
fire. Claims are reproduced, never trusted.
