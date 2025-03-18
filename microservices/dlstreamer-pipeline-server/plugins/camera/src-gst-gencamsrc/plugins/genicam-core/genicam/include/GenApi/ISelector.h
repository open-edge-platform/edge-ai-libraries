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
\brief    Definition of ISelector
*/

#ifndef GENAPI_ISELECTOR_H
#define GENAPI_ISELECTOR_H

#include <GenApi/GenApiDll.h>

#ifdef _MSC_VER
#   pragma warning ( push )
#   pragma warning ( disable : 4251 ) // XXX needs to have dll-interface to be used by clients of class YYY
#endif

namespace GENAPI_NAMESPACE
{
    /**
    \brief Interface for groups of features selected by a single one
    \ingroup GenApi_PublicImpl
    */
    interface GENAPI_DECL_ABSTRACT ISelector : virtual public IBase
    {
        //! true iff this feature selects a group of features
        virtual bool IsSelector() const = 0;

        //! retrieve the group of selected features
        virtual void GetSelectedFeatures( FeatureList_t& ) const = 0;

        //! retrieve the group of features selecting this node
        virtual void GetSelectingFeatures( FeatureList_t& ) const = 0;
    };

    //*************************************************************
    // CSelectorRef class
    //*************************************************************

    /**
    \internal
    \brief Reference to an ISelector pointer
    \ingroup GenApi_PublicImpl
    */
    template <class T>
    class CSelectorRefT : public CBaseRefT<T>
    {
        typedef CBaseRefT<T> ref;

    public:
        /*--------------------------------------------------------*/
        // ISelector
        /*--------------------------------------------------------*/

        //! Get all features of the Selector
        virtual void GetSelectedFeatures(FeatureList_t &Features) const
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->GetSelectedFeatures( Features );
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! retrieve the group of features selecting this node
        virtual void GetSelectingFeatures( FeatureList_t& Features) const
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->GetSelectingFeatures( Features );
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! true iff this feature selects a group of features
        virtual bool IsSelector() const
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->IsSelector();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }
    };

    //! Reference to an ISelector pointer
    //! \ingroup GenApi_PublicImpl
    typedef CSelectorRefT<ISelector> CSelectorRef;

}

#ifdef _MSC_VER
#   pragma warning ( pop )
#endif

#endif // GENAPI_ISELECTOR_H
