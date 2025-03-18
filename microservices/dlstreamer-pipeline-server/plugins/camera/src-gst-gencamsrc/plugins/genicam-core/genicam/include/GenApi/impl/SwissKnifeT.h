//-----------------------------------------------------------------------------
//  (c) 2005 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Margret Albrecht
//  $Header$
//-----------------------------------------------------------------------------
/*!
\file
\brief    Definition of the SwissknifeT class template
*/

#ifndef GENAPI_SWISSKNIFET_H
#define GENAPI_SWISSKNIFET_H

#include "GenApi/impl/Log.h"

namespace GENAPI_NAMESPACE
{
    /**
    \brief Implementation of the SwissKnife Interface
    */
    template<class Base>
    class SwissKnifeT : public Base
    {
    public:


        //! Implementation of SwissKnife::GetValue(double value)
        virtual double _GetValue(double value)
        {
            AutoLock l(Base::GetLock());

            GCLOG_INFO_PUSH(m_pValueLog)("_GetValue(value)...");
            double Value = Base::_GetValue(value);
            GCLOG_INFO_POP(m_pValueLog)("...GetValue(value) = %f", Value );

            return Value;

        }


    };



}

#endif