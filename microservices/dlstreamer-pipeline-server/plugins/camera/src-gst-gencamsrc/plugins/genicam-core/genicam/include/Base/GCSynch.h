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
\ingroup Base_PublicUtilities
*/

#ifndef GENAPI_GCSYNCH_H
#define GENAPI_GCSYNCH_H

#include <Base/GCTypes.h>
#include <Base/GCException.h>

#if defined (_WIN32)
#   include <windows.h>
#   include <winbase.h>
#elif defined (__GNUC__) && (defined (__linux__) || defined (__APPLE__))
#   include <semaphore.h>
#   include <pthread.h>
#   include <errno.h>
#   include <list>
#elif defined(VXWORKS)
   #include <vxworks.h>
   #include <taskLib.h>
#else
#   error No/unknown platform thread support
#endif

namespace GENICAM_NAMESPACE
{

    //-----------------------------------------------------------------
    // CLock
    //-----------------------------------------------------------------

    /**
    \brief A lock class
    \ingroup Base_PublicUtilities
    */
    class GCBASE_API CLock
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
    class GCBASE_API CLockEx : public CLock
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
    \ingroup Base_PublicUtilities
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


    /**
    \brief Named global lock which can be used over process boundaries
    \ingroup Base_PublicUtilities
    */
    class GCBASE_API CGlobalLock
    {
    public:
        //! Creates a global lock object name pszName.
        //! In case an object with the same name already exists
        //! a reference to the existing object will be created.
        //! If pszName is NULL an unnamed object will be created.
        explicit CGlobalLock(const char* pszName);
#if     defined(_WIN32) && ! defined(PHARLAP_WIN32)
        //! Creates a global lock object name pszName.
        //! In case an object with the same name already exists
        //! a reference to the existing object will be created.
        //! If pszName is NULL an unnamed object will be created.
        explicit CGlobalLock(const wchar_t* pszName);
#endif 
        //! Creates a global lock object name strName.
        //! In case an object with the same name already exists
        //! a reference to the existing object will be created.
        //! If strName is empty an unnamed object will be created.
        explicit CGlobalLock(const GENICAM_NAMESPACE::gcstring& strName);

        ~CGlobalLock();

    public:
        //! tests whether the lock is valid
        bool IsValid(void) const;

        //! enters the lock (may block)
        bool Lock(unsigned int timeout_ms);

        //! tries to enter the lock and returns immediately when not possible
        bool TryLock(void);

        //! leaves the lock
        void Unlock(void);

#if defined (__GNUC__) && (defined (__linux__) || defined (__APPLE__))
        // creates a hashed name instead of the real name
        void HashSemName(const GENICAM_NAMESPACE::gcstring& strName);
#endif

    protected:
#if defined(_WIN32)
        HANDLE m_handle;
#elif defined (__GNUC__) && (defined (__linux__) || defined (__APPLE__))
        GENICAM_NAMESPACE::gcstring m_semName;
        sem_t* m_handle;
#elif VXWORKS
        // There are no named locks on VxWorks. While we could use a single global lock, we
        // will just rely on the caller to add their own locking in
#else
#       error No/unknown platform thread support
#endif

        // This is for debugging/assertions only
        // the d'tor check whether this is 0 in debug builds
        // in release builds this is always 0
        mutable long m_DebugCount;

    private:
        // not copyable
        CGlobalLock(const CGlobalLock&);
        CGlobalLock& operator=(const CGlobalLock&);
    };


    /**
    \brief unlocks the global lock object on destruction

    This is for automatic UNLOCKING only.
    We can't do automatic locking here since there is no returnvalue for contructors

    \ingroup Base_PublicUtilities
    */
    //-----------------------------------------------------------------
    // unlocks the global lock object on destruction
    // this is for automatic UNLOCKING only.
    // we can't do automatic locking here since we don't get a returnvalue from the c'tor
    //-----------------------------------------------------------------
    class GCBASE_API CGlobalLockUnlocker
    {
    protected:
        CGlobalLock&    m_Lock;
        bool            m_enabled;

    public:
        CGlobalLockUnlocker(CGlobalLock& lock)
            : m_Lock(lock)
            , m_enabled(true) // this allows the auto unlock to be turned off for messy code structures
        {
            // explicitly don't lock the object here since we want to do this manually and handle the return value properly
        }

        ~CGlobalLockUnlocker()
        {
            UnlockEarly();
        }

        //! This function allows to unlock the object early before the object is destroyed
        void UnlockEarly(void)
        {
            if (m_enabled)
            {
                m_enabled = false;
                m_Lock.Unlock();
            }
        }

    private:
        CGlobalLockUnlocker& operator=(const CGlobalLockUnlocker&);
        CGlobalLockUnlocker(const CGlobalLockUnlocker&);
    };

} // namespace GenICam

#endif // GENAPI_GCSYNCH_H
