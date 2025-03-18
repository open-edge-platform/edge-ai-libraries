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
\ingroup GenApi_PublicInterface
*/

#ifndef GENAPI_IENUMENTRY_H
#define GENAPI_IENUMENTRY_H


#include <Base/GCString.h>
#include <GenApi/GenApiDll.h>
#include <GenApi/IValue.h>

#ifdef _MSC_VER
#   pragma warning ( push )
#   pragma warning ( disable : 4251 ) // XXX needs to have dll-interface to be used by clients of class YYY
#endif

namespace GENAPI_NAMESPACE
{

    //*************************************************************
    // IEnumEntry interface
    //*************************************************************

    /**
    \brief Interface of single enum value
    \ingroup GenApi_PublicInterface
    */
    /*! Maps of Enum Values to symbolic values */
    interface GENAPI_DECL_ABSTRACT IEnumEntry  : virtual public IValue
    {

    public:
        //! Get numeric enum value
        virtual int64_t GetValue() = 0;

        //! Get symbolic enum value
        virtual GENICAM_NAMESPACE::gcstring GetSymbolic()const = 0;

        //! Get double number associated with the entry
        virtual double GetNumericValue() = 0;

        //! Indicates if the corresponding EnumEntry is self clearing
        virtual bool IsSelfClearing() = 0;
    };

    //*************************************************************
    // CEnumEntryRef class
    //*************************************************************

#ifndef DOXYGEN_IGNORE

    /**
    \internal
    \brief Reference to an IEnumEntry pointer
    \ingroup GenApi_PublicImpl
    */
    template <class T>
    class CEnumEntryRefT : public CValueRefT<T>
    {
        typedef CValueRefT<T> ref;

    public:
        /*--------------------------------------------------------*/
        // IEnumEntry
        /*--------------------------------------------------------*/

        //! Get numeric enum value
        virtual int64_t GetValue()
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->GetValue();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Get symbolic enum value
        virtual    GENICAM_NAMESPACE::gcstring GetSymbolic()const
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->GetSymbolic();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Get numeric enum value
        virtual double GetNumericValue()
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->GetNumericValue();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Indicates if the corresponding EnumEntry is self clearing
        virtual bool IsSelfClearing()
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->IsSelfClearing();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }
    };

    //! Reference to an IEnumEntry pointer
    //! \ingroup GenApi_PublicImpl
    typedef CEnumEntryRefT<IEnumEntry> CEnumEntryRef;

#endif

}

#ifdef _MSC_VER
#   pragma warning ( pop )
#endif

#endif // ifndef GENAPI_IENUMENTRY_H
