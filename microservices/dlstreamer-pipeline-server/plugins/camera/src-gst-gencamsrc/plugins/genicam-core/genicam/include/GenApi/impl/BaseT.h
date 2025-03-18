//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Alexander Happe
//  $Header$
//
//  License: This file is published under the license of the EMVA GenICam  Standard Group.
//  A text file describing the legal terms is included in  your installation as 'GenICam_license.pdf'.
//  If for some reason you are missing  this file please contact the EMVA or visit the website
//  (http://www.genicam.org) for a full copy.
//
//  THIS SOFTWARE IS PROVIDED BY THE EMVA GENICAM STANDARD GROUP "AS IS"
//  AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
//  THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
//  PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE EMVA GENICAM STANDARD  GROUP
//  OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,  SPECIAL,
//  EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT  LIMITED TO,
//  PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,  DATA, OR PROFITS;
//  OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY  THEORY OF LIABILITY,
//  WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT  (INCLUDING NEGLIGENCE OR OTHERWISE)
//  ARISING IN ANY WAY OUT OF THE USE  OF THIS SOFTWARE, EVEN IF ADVISED OF THE
//  POSSIBILITY OF SUCH DAMAGE.
//-----------------------------------------------------------------------------
/*!
\file
\brief    Definition of the BaseT class template
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_BASET_H
#define GENAPI_BASET_H

#include "../Synch.h"
#include "../IBase.h"
#include "../EnumClasses.h"
#include "GenApi/impl/Log.h"
#include "Exception.h"



namespace GENAPI_NAMESPACE
{
    /**
        \brief Implementation of the IBase interface
    */
    template<class Base>
    class BaseT : public Base
    {
    public:
        //! Implementation of IBase::GetAccessMode()
        virtual EAccessMode GetAccessMode() const
        {
            AutoLock l(Base::GetLock());

            // Use cache
            #if ! defined( DISABLE_ACCESS_MODE_CACHING ) || (DISABLE_ACCESS_MODE_CACHING == 0)
#pragma BullseyeCoverage off
            if (    _UndefinedAccesMode != Base::m_AccessModeCache
                 && _CycleDetectAccesMode != Base::m_AccessModeCache
                )
#pragma BullseyeCoverage on
            {
                    EAccessMode AccessMode  = Combine(Base::m_AccessModeCache, Base::m_ImposedAccessMode);
                    GCLOGINFO( Base::m_pAccessLog, "GetAccessMode = '%s' (from cache)", EAccessModeClass::ToString(AccessMode).c_str() );

                    return AccessMode;
                }

            #endif

            typename Base::EntryMethodFinalizer E( this, meGetAccessMode );
        
            GCLOGINFOPUSH( Base::m_pAccessLog, "GetAccessMode...");

            EAccessMode NaturalAccessMode = Base::InternalGetAccessMode();

            EAccessMode AccessMode = Combine(NaturalAccessMode, Base::m_ImposedAccessMode);
            GCLOGINFOPOP( Base::m_pAccessLog, "...GetAccessMode = '%s' ", EAccessModeClass::ToString(AccessMode).c_str() );

            return AccessMode;

        }

    };
}

#endif
