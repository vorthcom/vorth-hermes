# Vorth plugin — after install

Two steps and you're live on the beta:

**1. Add the provider to your `config.yaml`:**

No key yet? Use `VORTH_API_KEY=vorth-walkin` for now — the maître d'
will explain how reservations work when you knock.

```yaml
providers:
  vorth:
    base_url: https://dribnet--vorth-vorthcore-v2dev-vanilla.modal.run/v1
    key_env: VORTH_API_KEY
    models:
      beta-deepseek-v4-flash-0731:
        context_length: 261120
```

(The `context_length` override matters: public registries list this
model at its vendor-advertised 1M; the beta serves a declared 262,144
envelope, and 261,120 gives your client a 1,024-token planning cushion.)

**2. Enable the plugin** in `config.yaml`

(v0.4.1: the plugin self-installs its model-provider profile into
`plugins/model-providers/vorth` on first load — you'll see a one-line
notice; restart Hermes once after that so the provider registers.)

Enable (`plugins.enabled: [vorth]`)
and restart Hermes. Switch models with `/model` →
`beta-deepseek-v4-flash-0731`.

What the sentinel does: five deterministic detectors (empty answer,
loop, malformed tool call, request echo, truncation stub) watch every
response, observe-only. Detector fires become replayable forensic
capsules shipped to the Vorth mothership, where every claim is
re-executed before it is believed. That loop is why beta inference is
free: your sessions are the sensor network.

Updating later: `hermes plugins update vorth` (or the dashboard button).

Optional fun: `VORTH_SIGNAGE=1` enables the front-of-house costumes:
the big CLOSED door-sign on closed-hours refusals (terminal ≥ 60×18),
one-liner fallbacks otherwise. Copy desk at the top of `signage.py`.
