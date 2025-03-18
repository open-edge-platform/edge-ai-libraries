//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Fritz Dierks
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
\brief    Definition of the interface IValue.
\ingroup GenApi_PublicInterface
*/

#ifndef GENAPI_IVALUE_H
#define GENAPI_IVALUE_H

#include <GenApi/GenApiDll.h>
#include <GenApi/Types.h>
#include <GenApi/IBase.h>
#include <GenApi/INode.h>
#include <Base/GCString.h>
#include <Base/GCException.h>

#ifdef _MSC_VER
#   pragma warning ( push )
#   pragma warning ( disable : 4251 ) // XXX needs to have dll-interface to be used by clients of class YYY
#endif

namespace GENAPI_NAMESPACE
{
    interface INode;

    //*************************************************************
    // IValue interface
    //*************************************************************

    /**
    \brief Interface for value properties
    \ingroup GenApi_PublicInterface
    */
    interface GENAPI_DECL_ABSTRACT IValue : virtual public IBase
    {
        //! Get the INode interface of the node
        virtual INode* GetNode() { return dynamic_cast<INode*>(this); }

        //! Get content of the node as string
        /*!
        \param Verify Enables Range verification (default = false). The AccessMode is always checked
        \param IgnoreCache If true the value is read ignoring any caches (default = false)
        \return The value read
        */
        virtual GENICAM_NAMESPACE::gcstring ToString(bool Verify = false, bool IgnoreCache = false) = 0;

        //! Set content of the node as string
        /*!
        \param ValueStr The value to set
        \param Verify Enables AccessMode and Range verification (default = true)
        */
        virtual void FromString(const GENICAM_NAMESPACE::gcstring& ValueStr, bool Verify = true) = 0;

        //! Checks if the value comes from cache or is requested from another node
        virtual bool IsValueCacheValid() const = 0;
    };


    //*************************************************************
    // CValueRef class
    //*************************************************************

#ifndef DOXYGEN_IGNORE

    /**
    \internal
    \brief Reference to an IValue pointer
    \ingroup GenApi_PublicImpl
    */
    template <class T, class I=T>
    class CValueRefT : public CBaseRefT<T,I>
    {
        typedef CBaseRefT<T, I> ref;

    public:
        /*--------------------------------------------------------*/
        // IValue
        /*--------------------------------------------------------*/

        //! Get the INode interface of the node
        virtual INode* GetNode()
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->GetNode();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Get content of the node as string
        virtual GENICAM_NAMESPACE::gcstring ToString(bool Verify = false, bool IgnoreCache = false)
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->ToString(Verify, IgnoreCache);
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Set content of the node as string
        virtual void FromString(const GENICAM_NAMESPACE::gcstring& ValueStr, bool Verify = true)
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->FromString(ValueStr, Verify);
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Checks if the value comes from cache or is requested from another node
        virtual bool IsValueCacheValid() const
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->IsValueCacheValid();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }
    };

    //! Reference to an IValue pointer
    //! \ingroup GenApi_PublicImpl
    typedef CValueRefT<IValue> CValueRef;

#endif

}

#ifdef _MSC_VER
#   pragma warning ( pop )
#endif

#endif // ifndef GENAPI_IVALUE_H
