const API_BASE = (import.meta.env.VITE_BACKEND_API_BASE || "").replace(/\/$/, "");
const POLL_MS = Number(import.meta.env.VITE_REGISTRATION_POLL_MS || 2000);
const DUMMY_EPC_PREFIX = "E28068940000400386621";

export function subscribeCurrentScan(_scanId, callback, onError) {
  return poll(async () => {
    const payload = await requestJson("/v1/registration-challenges/current");
    callback(payload.challenge ? normalizeChallenge(payload.challenge) : null);
  }, onError);
}

export function subscribePendingScans(callback, onError) {
  return poll(async () => {
    const payload = await requestJson("/v1/registration-challenges/pending");
    callback((payload.challenges || []).map(normalizeChallenge));
  }, onError);
}

export function subscribeRegistrations(callback, onError) {
  return poll(async () => {
    const payload = await requestJson("/v1/tag-bindings");
    callback((payload.bindings || []).map(normalizeBinding));
  }, onError);
}

export async function createPendingScan(goodsId) {
  return requestJson("/internal/registration-challenges", {
    method: "POST",
    body: {
      siteId: import.meta.env.VITE_REGISTRATION_SITE_ID || "suwon_01",
      readerId: import.meta.env.VITE_REGISTRATION_READER_ID || "rp_001",
      epc: goodsId,
      claimBaseUrl: import.meta.env.VITE_QR_CLAIM_BASE_URL || "khuround://tag-bindings/claim",
    },
  });
}

export function createDummyEpc() {
  const suffix = Math.floor(Math.random() * 0xfff).toString(16).toUpperCase().padStart(3, "0");
  return `${DUMMY_EPC_PREFIX}${suffix}`;
}

export async function markScanRegistered(scanId) {
  if (!scanId) return;
  await deleteScan(scanId);
}

export async function deleteScan(scanId) {
  if (!scanId) return;
  await requestJson(`/internal/registration-challenges/${encodeURIComponent(scanId)}`, {
    method: "DELETE",
  });
}

export function buildRegisterUrl(tokenOrUrl) {
  if (!tokenOrUrl) return "";
  if (/^[a-z][a-z0-9+.-]*:/i.test(tokenOrUrl)) {
    return tokenOrUrl;
  }
  const baseUrl = import.meta.env.VITE_QR_CLAIM_BASE_URL || "khuround://tag-bindings/claim";
  const separator = baseUrl.includes("?") ? "&" : "?";
  return `${baseUrl}${separator}token=${encodeURIComponent(tokenOrUrl)}`;
}

function poll(task, onError) {
  let active = true;
  let timer = null;

  async function tick() {
    try {
      await task();
    } catch (error) {
      if (onError) onError(error);
    } finally {
      if (active) {
        timer = window.setTimeout(tick, POLL_MS);
      }
    }
  }

  tick();
  return () => {
    active = false;
    if (timer) window.clearTimeout(timer);
  };
}

async function requestJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method || "GET",
    headers: { "Content-Type": "application/json" },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.message || payload.errorCode || "등록 API 요청에 실패했습니다.");
  }
  return payload;
}

function normalizeChallenge(challenge) {
  return {
    id: challenge.challengeId,
    goodsId: challenge.epc,
    ott: challenge.claimUrl,
    claimUrl: challenge.claimUrl,
    status: challenge.status?.toLowerCase?.() || "pending",
    createdAt: challenge.createdAt ? new Date(challenge.createdAt) : null,
    expiresAt: challenge.expiresAt ? new Date(challenge.expiresAt) : null,
  };
}

function normalizeBinding(binding) {
  return {
    id: binding.tagBindingId,
    goodsId: binding.epc,
    displayName: "익명 앱",
    userEmail: binding.clientId,
    registeredAt: binding.boundAt ? new Date(binding.boundAt) : null,
  };
}
