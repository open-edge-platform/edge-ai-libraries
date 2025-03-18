//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Hartmut Nebelung
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
\brief    Definition of CValueCache
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_VALUECACHE_H
#define GENAPI_VALUECACHE_H

#include "../Synch.h"
#include "../Types.h"

namespace GENAPI_NAMESPACE
{
    struct CValueCacheImpl;

    /**
    * \ingroup internal_impl
    *
    * \brief Cache for Registervalues
    */
    class CValueCache : public LockableObject< CValueCache >
    {
    public:
        CValueCache();
        ~CValueCache();

        /// Look up a value
        void GetValue( int64_t Address, uint32_t Size, void *pValue ) const;

        /// Enter a new value
        void SetValue( int64_t Address, uint32_t Size, const void *pValue );

        /// Invalidate a value
        void InvalidateValue( int64_t Address );

        /// Query whether value is valid
        bool IsValueValid( int64_t Address, uint32_t Size ) const;

        /// Query wheher value is implemented
        //bool IsValuePresent( int64_t Address ) const;

        /// Clear all entries
        //void ClearAllEntries();

    private:
        /// not implemented: copy constructor
        CValueCache( const CValueCache& );

        /// not implmeneted: assignment operator
        CValueCache& operator=( const CValueCache& );

    private:

        CValueCacheImpl* m_pImpl;
    };
}

#endif // GENAPI_VALUECACHE_H


