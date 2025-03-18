//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Margret Albrecht
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
\brief    Definition of RegisterList_t type and the interface IRegister
\ingroup GenApi_PublicInterface
*/

#ifndef GENAPI_IREGISTER_H
#define GENAPI_IREGISTER_H

#include <GenApi/GenApiDll.h>
#include <GenApi/Types.h>
#include <GenApi/IValue.h>

#ifdef _MSC_VER
#   pragma warning ( push )
#   pragma warning ( disable : 4251 ) // XXX needs to have dll-interface to be used by clients of class YYY
#endif

namespace GENAPI_NAMESPACE
{
    //*************************************************************
    // IRegister interface
    //*************************************************************

    /**
    \brief Interface for registers
    \ingroup GenApi_PublicInterface
    */
    interface GENAPI_DECL_ABSTRACT IRegister  : virtual public IValue
    {
        //! Set the register's contents
        /*!
        \param pBuffer The buffer containing the data to set
        \param Length The number of bytes in pBuffer
        \param Verify Enables AccessMode and Range verification (default = true)
        */
        virtual void Set(const uint8_t *pBuffer, int64_t Length, bool Verify = true) = 0;

        //! Fills a buffer with the register's contents
        /*!
        \param pBuffer The buffer receiving the data to read
        \param Length The number of bytes to retrieve
        \param Verify Enables Range verification (default = false). The AccessMode is always checked
        \param IgnoreCache If true the value is read ignoring any caches (default = false)
        */
        virtual void Get(uint8_t *pBuffer, int64_t Length, bool Verify = false, bool IgnoreCache = false) = 0;

        //! Retrieves the Length of the register [Bytes]
        virtual int64_t GetLength() = 0;

        //! Retrieves the Address of the register
        virtual int64_t GetAddress() = 0;
    };

    //*************************************************************
    // CRegisterRef class
    //*************************************************************


#ifndef DOXYGEN_IGNORE

    /**
    \internal
    \brief Reference to an IRegister pointer
    \ingroup GenApi_PublicImpl
    */
    template <class T>
    class CRegisterRefT : public CValueRefT<T>
    {
        typedef CValueRefT<T> ref;

    public:
        /*--------------------------------------------------------*/
        // IRegister
        /*--------------------------------------------------------*/

        //! Set the register's contents
        virtual void Set(const uint8_t *pBuffer, int64_t Length, bool Verify = true)
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->Set(pBuffer, Length, Verify);
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Fills a buffer with the register's contents
        virtual void Get(uint8_t *pBuffer, int64_t Length, bool Verify = false, bool IgnoreCache = false)
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->Get(pBuffer, Length, Verify, IgnoreCache);
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Retrieves the Length of the register [Bytes]
        virtual int64_t GetLength()
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->GetLength();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Retrieves the Address of the register
        virtual int64_t GetAddress()
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->GetAddress();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

    };

    //! Reference to an IRegister pointer
    //! \ingroup GenApi_PublicImpl
    typedef CRegisterRefT<IRegister> CRegisterRef;

#endif

}

#ifdef _MSC_VER
#   pragma warning ( pop )
#endif

#endif // ifndef GENAPI_IREGISTER_H
