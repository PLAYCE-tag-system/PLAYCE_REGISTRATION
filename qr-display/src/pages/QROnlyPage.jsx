import { useEffect, useMemo, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { motion } from "framer-motion";
import { buildRegisterUrl, createDummyEpc, createPendingScan, subscribeCurrentScan } from "../lib/registrationApi.js";

export default function QROnlyPage() {
  const [scanId, setScanId] = useState(() => localStorage.getItem("active_qr_id"));
  const [currentScan, setCurrentScan] = useState(null);
  const [error, setError] = useState("");
  const [isCreatingDummy, setIsCreatingDummy] = useState(false);

  // 로컬 스토리지 변경 감지 (다른 탭의 관리자 페이지에서 큐를 클릭할 때마다 실행)
  useEffect(() => {
    const handleStorageChange = (e) => {
      if (e.key === "active_qr_id") {
        setScanId(e.newValue);
      }
    };
    window.addEventListener("storage", handleStorageChange);
    return () => window.removeEventListener("storage", handleStorageChange);
  }, []);

  useEffect(() => {
    const unsubscribeScan = subscribeCurrentScan(scanId, setCurrentScan, console.error);
    return () => unsubscribeScan();
  }, [scanId]);

  const registerUrl = useMemo(
    () => (currentScan?.claimUrl || currentScan?.ott ? buildRegisterUrl(currentScan.claimUrl || currentScan.ott) : ""),
    [currentScan],
  );

  async function createDummyScan() {
    setIsCreatingDummy(true);
    setError("");
    try {
      const challenge = await createPendingScan(createDummyEpc());
      const normalized = {
        id: challenge.challengeId,
        goodsId: challenge.epc,
        claimUrl: challenge.claimUrl,
        status: challenge.status?.toLowerCase?.() || "pending",
        createdAt: challenge.createdAt ? new Date(challenge.createdAt) : null,
        expiresAt: challenge.expiresAt ? new Date(challenge.expiresAt) : null,
      };
      setScanId(challenge.challengeId);
      setCurrentScan(normalized);
      localStorage.setItem("active_qr_id", challenge.challengeId);
    } catch (scanError) {
      setError(scanError.message);
    } finally {
      setIsCreatingDummy(false);
    }
  }

  return (
    <div className="flex min-h-screen w-full flex-col items-center justify-center bg-black p-8">
      <div className="fixed right-5 top-5 z-10 flex items-center gap-3">
        {error && <p className="max-w-80 rounded-md bg-danger/15 px-3 py-2 text-sm text-danger">{error}</p>}
        <button
          className="rounded-md bg-white px-4 py-2 text-sm font-bold text-black transition-colors hover:bg-slate-200 disabled:cursor-wait disabled:opacity-60"
          disabled={isCreatingDummy}
          onClick={createDummyScan}
          type="button"
        >
          {isCreatingDummy ? "생성 중" : "더미 태그 인식"}
        </button>
      </div>
      {currentScan && registerUrl ? (
        <motion.div
          key={currentScan.id}
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex flex-col items-center gap-8"
        >
          <div className="rounded-2xl bg-white p-8 sm:p-12">
            <QRCodeSVG value={registerUrl} size={400} level="H" includeMargin />
          </div>
          <div className="text-center">
            <h1 className="text-3xl font-black text-white sm:text-4xl">앱 프로필 탭에서 QR을 스캔해주세요</h1>
          </div>
        </motion.div>
      ) : (
        <div className="flex flex-col items-center gap-6 text-center">
          <div className="flex h-32 w-32 items-center justify-center rounded-2xl border-4 border-dashed border-white/20">
            <span className="text-4xl text-white/20">?</span>
          </div>
          <h1 className="text-3xl font-bold text-slate-400">대기 중인 스캔이 없습니다</h1>
          <p className="text-xl text-slate-500">등록용 리더기에 태그를 올리면 QR 코드가 나타납니다.</p>
          <button
            className="rounded-md bg-white px-5 py-3 text-base font-bold text-black transition-colors hover:bg-slate-200 disabled:cursor-wait disabled:opacity-60"
            disabled={isCreatingDummy}
            onClick={createDummyScan}
            type="button"
          >
            {isCreatingDummy ? "생성 중" : "더미 태그 인식"}
          </button>
        </div>
      )}
    </div>
  );
}
