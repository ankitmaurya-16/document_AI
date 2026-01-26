import React, { useEffect, useState } from "react"
import Loading from './Loading'
import { dummyPlans } from '../assets/assets'

const Credits = () => {
  const [plans, setPlans] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const fetchPlans = async () => {
    setPlans(dummyPlans)
    setLoading(false)
  }
  useEffect(() => {
    fetchPlans()
  },[])
  if (loading) return <Loading/>
  return (
    <div className='max-w-7xl h-screen overflow-y-scroll mx-auto px-4 sm:px-6 lg:px-8 py-12'> 
      <h2 className='text-3xl font-semibold text-center mb-10 xl:mt-30 text-gray-800 dark:text-white'>Credit Plans</h2>
      <div className="flex flex-wrap justify-center gap-8">
        {plans.map((plan)=>(
          <div key={plan._id} className={`border border-gray-200 dark:border-neutral-700 rounded-lg shadow hover:shadow-lg transition-shadow p-6 min-w-[300px] flex flex-col ${plan._id==="pro"?"bg-gray-50 dark:bg-neutral-900":"bg-white dark:bg-neutral-800/30"}`}>
            <div className="flex-1">
              <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">{plan.name}</h3>
              <p className="text-2xl font-bold text-[#2f198a] dark:text-[#3D81F6] mb-4">${plan.price}
                <span className="text-base font-normal text-gray-600 dark:text-neutral-400">{' '}/ {plan.credits} credits</span>
              </p>
              <ul>
                {
                  plan.features.map((feature, index)=>(
                    <li key={index} className="flex items-center mb-2">
                      <span className="text-[#2f198a] dark:text-[#3D81F6] mr-2">✔</span>
                      <span className="text-gray-700 dark:text-white">{feature}</span>
                    </li>
                  ))
                }
              </ul>
            </div>
            <button className="mt-4 bg-gradient-to-r from-[#2f198a] to-[#3D81F6] text-white px-4 py-2 rounded hover:opacity-90 transition">Buy Now</button>
          </div>
        ))}

      </div>
    </div>
  )
}

export default Credits
