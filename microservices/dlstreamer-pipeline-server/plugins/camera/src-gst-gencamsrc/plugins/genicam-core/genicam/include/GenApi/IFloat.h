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
\brief    Definition of the IFloat interface
\ingroup GenApi_PublicInterface
*/

#ifndef GENAPI_IFLOAT_H
#define GENAPI_IFLOAT_H

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
    // IFloat interface
    //*************************************************************

    /**
    \brief Interface for float properties
    \ingroup GenApi_PublicInterface
    */
    interface GENAPI_DECL_ABSTRACT IFloat  : virtual public IValue
    {
        //! Set node value
        /*!
        \param Value The value to set
        \param Verify Enables AccessMode and Range verification (default = true)
        */
        virtual void SetValue(double Value, bool Verify = true) = 0;

        //! Set node value
        virtual IFloat& operator=(double Value) = 0;

        //! Get node value
        /*!
        \param Verify Enables Range verification (default = false). The AccessMode is always checked
        \param IgnoreCache If true the value is read ignoring any caches (default = false)
        \return The value read
        */
        virtual double GetValue(bool Verify = false, bool IgnoreCache = false) = 0;

        //! Get node value
        virtual double operator()() = 0;

        //! Get node value
        virtual double operator*() = 0;

        //! Get minimum value allowed
        virtual double GetMin() = 0;

        //! Get maximum value allowed
        virtual double GetMax() = 0;

        //! True if the float has a constant increment
        virtual bool HasInc() = 0;

        //! Get increment mode
        virtual EIncMode GetIncMode() = 0;

        //! Get the constant increment if there is any
        virtual double GetInc() = 0;

        //! Get list of valid value
        virtual double_autovector_t GetListOfValidValues( bool bounded = true) = 0;

        //! Get recommended representation
        virtual  ERepresentation GetRepresentation() = 0;

        //! Get the physical unit name
        virtual GENICAM_NAMESPACE::gcstring GetUnit() const = 0;

        //! Get the way the float should be converted to a string
        virtual EDisplayNotation GetDisplayNotation() const = 0;

        //! Get the precision to be used when converting the float to a string
        virtual int64_t GetDisplayPrecision() const = 0;

        //! Restrict minimum value
        virtual void ImposeMin(double Value) = 0;

        //! Restrict maximum value
        virtual void ImposeMax(double Value) = 0;
    };

    //*************************************************************
    // CFloatRef class
    //*************************************************************

    interface IInteger;
    interface IEnumeration;

#ifndef DOXYGEN_IGNORE

    /**
    \internal
    \brief Reference to an IEnumEntry pointer
    \ingroup GenApi_PublicImpl
    */
    template <class T>
    class CFloatRefT : public CValueRefT<T>
    {
        typedef CValueRefT<T> ref;

    public:
        /*--------------------------------------------------------*/
        // IFloat
        /*--------------------------------------------------------*/

        //! Set node value
        virtual void SetValue(double Value, bool Verify = true)
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->SetValue(Value, Verify);
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Set node value
        virtual IFloat& operator=(double Value)
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->operator=(Value);
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Get node value
        virtual double GetValue(bool Verify = false, bool IgnoreCache = false)
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->GetValue(Verify, IgnoreCache);
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Get node value
        virtual double operator()()
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->operator()();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Get node value
        virtual double operator*()
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->operator*();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Get minimum value allowed
        virtual double GetMin()
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->GetMin();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Get maximum value allowed
        virtual double GetMax()
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->GetMax();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! True if the float has a constant increment
        virtual bool HasInc()
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->HasInc();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }
        virtual EIncMode GetIncMode()
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->GetIncMode();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Get the constant increment if there is any
        virtual double GetInc()
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->GetInc();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Get list of valid value
        virtual double_autovector_t GetListOfValidValues(bool bounded = true)
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->GetListOfValidValues(bounded);
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Get recommended representation
        virtual  ERepresentation GetRepresentation()
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->GetRepresentation();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Get unit
        virtual GENICAM_NAMESPACE::gcstring GetUnit() const
        {
            if (ref::m_Ptr)
                return ref::m_Ptr->GetUnit();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Get the way the float should be converted to a string
        virtual EDisplayNotation GetDisplayNotation() const
        {
            if (ref::m_Ptr)
                return ref::m_Ptr->GetDisplayNotation();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Get the precision to be used when converting the float to a string
        virtual int64_t GetDisplayPrecision() const
        {
            if (ref::m_Ptr)
                return ref::m_Ptr->GetDisplayPrecision();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! gets the interface of an alias node.
        IInteger *GetIntAlias()
        {
            if (ref::m_Ptr)
                return dynamic_cast<IInteger*>(ref::m_Ptr->GetNode()->GetCastAlias());
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! gets the interface of an alias node.
        IEnumeration *GetEnumAlias()
        {
            if (ref::m_Ptr)
                return dynamic_cast<IEnumeration*>(ref::m_Ptr->GetNode()->GetCastAlias());
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Restrict minimum value
        virtual void ImposeMin(double Value)
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->ImposeMin(Value);
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! Restrict maximum value
        virtual void ImposeMax(double Value)
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->ImposeMax(Value);
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

    };

    //! Reference to an IFloat pointer
    //! \ingroup GenApi_PublicImpl
    typedef CFloatRefT<IFloat> CFloatRef;

#endif

}

#ifdef _MSC_VER
#   pragma warning ( pop )
#endif

#endif // ifndef GENAPI_IFLOAT_H
