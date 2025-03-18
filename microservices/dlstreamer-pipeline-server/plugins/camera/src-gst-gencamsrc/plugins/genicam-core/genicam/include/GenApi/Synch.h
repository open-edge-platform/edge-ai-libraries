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
\brief    Definition of Lock classes
\ingroup GenApi_PublicImpl
*/

#ifndef GENAPI_SYNCH_H
#define GENAPI_SYNCH_H

#include <GenApi/GenApiDll.h>
#include <Base/GCException.h>

#if defined (_WIN32)
#   include <windows.h>
#   include <winbase.h>
#elif defined (__GNUC__) && (defined (__linux__) || defined (__APPLE__))
#   include <pthread.h>
#   include <errno.h>
#   include <list>
#elif defined(VXWORKS)
   #include <vxworks.h>
   #include <intLib.h>
   #include <taskLib.h>
#else
#   error No/unknown platform thread support
#endif

namespace GENAPI_NAMESPACE
{

    //-----------------------------------------------------------------
    // CLock
    //-----------------------------------------------------------------

    /**
    \brief A lock class
    \ingroup GenApi_PublicImpl
    */
    class GENAPI_DECL CLock
    {
    public:
        //! Constructor
        CLock();

        //! Destructor
        ~CLock();

        //! tries to enter the critical section; returns true if successful
        bool TryLock();

        //! enters the critical section (may block)
        void Lock();

        //! leaves the critical section
        void Unlock();

    private:
        //! no copy constructor
        CLock( const CLock& );

        //! no assignment operator
        CLock& operator=( const CLock& );

    protected:

#if defined (_WIN32)
        //! The critical section object
        CRITICAL_SECTION m_csObject;
#elif defined (__GNUC__) && (defined (__linux__) || defined (__APPLE__))
        //! the mutex object
        pthread_mutex_t m_mtxObject;
#elif defined(VXWORKS)
        SEM_ID m_sem;
#else
#       error No/unknown platform thread support
#endif

    };


    //! This class is for testing purposes only. It should not be used for
    //! client code because it exists only for Windows but not for Linux
    //! since it uses internal data structures of a Win32 object
    class GENAPI_DECL CLockEx : public CLock
    {
    public:

#       if defined (_WIN32)

            //! Gives access to internal data member for test and purposes
            int64_t GetLockCount();

            //! Gives access to internal data member for test and purposes
            int64_t GetRecursionCount();

#       elif defined (__GNUC__) && (defined (__linux__) || defined (__APPLE__) || defined(VXWORKS))
            // nothing implemented for Unix
#       else
#           error No/unknown platform support
#       endif

    private:
        //! no copy constructor
        CLockEx( const CLockEx& );

        //! no assignment operator
        CLockEx& operator=( const CLockEx& );

    };


    //-----------------------------------------------------------------
    // AutoLock
    //-----------------------------------------------------------------
    class AutoLock
    {
        CLock& m_Lock;
    public:
        AutoLock(CLock& lock)
            : m_Lock(lock)
        {
            m_Lock.Lock();
        }

        ~AutoLock()
        {
            m_Lock.Unlock();
        }

    private:
        AutoLock& operator=(const AutoLock&);
        AutoLock(const AutoLock&);
    };


    //-----------------------------------------------------------------
    // template LockableObject<Object,ThreadingModel>
    //-----------------------------------------------------------------

    /**
    \brief Instance-Lock for an object
    \ingroup GenApi_PublicImpl
    */
    template< class Object>
    class LockableObject
    {
    public:
        mutable CLock m_Lock;

        class Lock;
        friend class Lock;

        /*! A scopelevel Lock class.
        * Automatically acquires the lock when created and releases
        * it when destroyed.
        */
        class Lock
        {
            /// Reference to outer object
            const LockableObject<Object> &m_Object;
        public:
            Lock( const LockableObject<Object>& obj) : m_Object(obj) {
                m_Object.m_Lock.Lock();
            }

            ~Lock(){
                m_Object.m_Lock.Unlock();
            }
        private:
            Lock& operator=( const Lock& );
        };

        /// Get a new lock
        Lock GetLock() const
        {
            return Lock( *this );
        }
    };

} // namespace GenApi

#endif // GENAPI_SYNCH_H
