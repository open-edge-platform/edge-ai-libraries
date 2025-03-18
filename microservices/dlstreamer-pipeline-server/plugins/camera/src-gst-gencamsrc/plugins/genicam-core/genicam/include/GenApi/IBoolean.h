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
\brief    Definition of IBoolean interface
\ingroup GenApi_PublicInterface
*/

#ifndef GENAPI_IBOOLEAN_H
#define GENAPI_IBOOLEAN_H

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
    // IBoolean interface
    //*************************************************************

    /**
    \brief Interface for Boolean  properties
    \ingroup GenApi_PublicInterface
    */
    interface GENAPI_DECL_ABSTRACT IBoolean   : virtual public IValue
    {
    public:
        //! Set node value
        /*!
        \param Value The value to set
        \param Verify Enables AccessMode and Range verification (default = true)
        */
        virtual void SetValue(bool Value, bool Verify = true) = 0;

        //! Set node value
        virtual void operator=(bool Value){ SetValue( Value ); }

        //! Get node value
        /*!
        \param Verify Enables Range verification (default = false). The AccessMode is always checked
        \param IgnoreCache If true the value is read ignoring any caches (default = false)
        \return The value read
        */
        virtual bool GetValue(bool Verify = false, bool IgnoreCache = false) const = 0;

        //! Get node value
        virtual bool operator()() const { return GetValue(); }
    };


    //*************************************************************
    // CBooleanRef class
    //*************************************************************

#ifndef DOXYGEN_IGNORE
    /**
    \internal
    \brief Reference to an IInteger pointer
    \ingroup GenApi_PublicImpl
    */
    template <class T>
    class CBooleanRefT : public CValueRefT<T>
    {
        typedef CValueRefT<T> ref;

    public:
        /*--------------------------------------------------------*/
        // IBoolean
        /*--------------------------------------------------------*/

        //! Set node value
        virtual void SetValue(bool Value, bool Verify = true)
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->SetValue(Value, Verify);
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");

            // unused param *JS* (removed warning)
            GC_UNUSED(Verify);
        }

        //! Set node value
        virtual void operator=(bool Value)
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->operator=(Value);
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Get node value
        virtual bool GetValue(bool Verify = false, bool IgnoreCache = false) const
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->GetValue(Verify, IgnoreCache);
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Get node value
        virtual bool operator()() const
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->operator()();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

    };

    //! Reference to an IBoolean pointer
    //! \ingroup GenApi_PublicImpl
    typedef CBooleanRefT<IBoolean> CBooleanRef;

#endif



}

#ifdef _MSC_VER
#   pragma warning ( pop )
#endif

#endif // ifndef GENAPI_IBOOLEAN_H
