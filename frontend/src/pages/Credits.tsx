import React, { useEffect, useState } from "react"
import { useLocation } from "react-router-dom"
import Loading from "./Loading"
import { useAppContext } from "../context/AppContext"

const Credits = () => {
  const { API_URL, startCheckout, user, refreshUser } = useAppContext()
  const location = useLocation()

  const [plans, setPlans] = useState([])
  const [loading, setLoading] = useState(true)
  const [buying, setBuying] = useState(null)
  const [error, setError] = useState(null)
  const [banner, setBanner] = useState(null)

  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const status = params.get("status")
    if (status === "success") {
      setBanner({ kind: "success", text: "Payment received — credits will be added shortly." })
      refreshUser?.()
    } else if (status === "cancel") {
      setBanner({ kind: "info", text: "Checkout cancelled. No charge was made." })
    }
  }, [location.search, refreshUser])

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/billing/plans`)
        const data = await res.json()
        if (!cancelled) setPlans(data.plans || [])
      } catch (e) {
        if (!cancelled) setError("Failed to load plans")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    run()
    return () => { cancelled = true }
  }, [API_URL])

  const handleBuy = async (planId) => {
    setError(null)
    setBuying(planId)
    const result = await startCheckout(planId)
    if (result?.error) {
      setError(result.error)
      setBuying(null)
    }
    // On success, browser redirects away — no need to reset state.
  }

  if (loading) return <Loading />

  return (
    <div className="max-w-7xl h-screen overflow-y-scroll mx-auto px-4 sm:px-6 lg:px-8 py-12">
      <h2 className="text-3xl font-semibold text-center mb-4 xl:mt-30 text-gray-800 dark:text-white">
        Credit Plans
      </h2>
      {user && (
        <p className="text-center text-sm text-gray-500 dark:text-neutral-400 mb-8">
          You have <span className="font-semibold text-[#3D81F6]">{user.credits}</span> credits.
        </p>
      )}

      {banner && (
        <div
          className={`max-w-2xl mx-auto mb-6 rounded-md border px-4 py-2 text-sm ${
            banner.kind === "success"
              ? "border-green-300 bg-green-50 text-green-800 dark:border-green-700 dark:bg-green-900/30 dark:text-green-200"
              : "border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-700 dark:bg-blue-900/30 dark:text-blue-200"
          }`}>
          {banner.text}
        </div>
      )}

      {error && (
        <div className="max-w-2xl mx-auto mb-6 rounded-md border border-red-300 bg-red-50 text-red-800 dark:border-red-700 dark:bg-red-900/30 dark:text-red-200 px-4 py-2 text-sm">
          {error}
        </div>
      )}

      <div className="flex flex-wrap justify-center gap-8">
        {plans.map((plan) => (
          <div
            key={plan._id}
            className={`border border-gray-200 dark:border-neutral-700 rounded-lg shadow hover:shadow-lg transition-shadow p-6 min-w-[300px] flex flex-col ${
              plan._id === "pro" ? "bg-blue-50 dark:bg-black/80" : "bg-white dark:bg-black/50"
            }`}>
            <div className="flex-1">
              <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">{plan.name}</h3>
              <p className="text-2xl font-bold text-[#3D81F6] mb-4">
                ${plan.price}
                <span className="text-base font-normal text-gray-600 dark:text-neutral-400">
                  {" "}/ {plan.credits} credits
                </span>
              </p>
              <ul>
                {plan.features.map((feature, index) => (
                  <li key={index} className="flex items-center mb-2">
                    <span className="text-[#3D81F6] mr-2">✔</span>
                    <span className="text-gray-700 dark:text-white">{feature}</span>
                  </li>
                ))}
              </ul>
            </div>
            <button
              onClick={() => handleBuy(plan._id)}
              disabled={buying !== null || !user}
              className="mt-4 bg-gradient-to-r from-[#2f198a] to-[#3D81F6] text-white px-4 py-2 rounded hover:opacity-90 transition disabled:opacity-50 disabled:cursor-not-allowed">
              {buying === plan._id ? "Redirecting…" : user ? "Buy Now" : "Login to buy"}
            </button>
          </div>
        ))}
      </div>

      <p className="text-center text-xs text-gray-400 dark:text-neutral-500 mt-10">
        Test mode — use card 4242 4242 4242 4242 with any future expiry and any CVC.
      </p>
    </div>
  )
}

export default Credits
