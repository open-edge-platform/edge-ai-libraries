//-----------------------------------------------------------------------------
//  (c) 2010 by Basler Vision Technologies
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
*/

#ifndef GENAPI_SELECTORDIGIT_H
#define GENAPI_SELECTORDIGIT_H

#include "GenApi/ISelectorDigit.h"
#include "GenApi/IBase.h"
#include "GenApi/INode.h"
#include "GenApi/Pointer.h"

#include <list>
#ifdef _MSC_VER
#   pragma warning ( disable : 4251 ) // XXX needs to have dll-interface to be used by clients of class YYY
#endif

namespace GENAPI_NAMESPACE
{
    //-------------------------------------------------

    //! A selector set counter digit formed by an enumeration
    class CEnumSelectorDigit : public ISelectorDigit
    {
    public:
        //! Constructor
        CEnumSelectorDigit( 
            IBase *pBase //!> Node covered by this digit
            );

        // Implementation of ISelectorDigit
    public:
        virtual bool SetFirst();
        virtual bool SetNext(bool Tick = true);
        virtual void Restore();
        virtual GENICAM_NAMESPACE::gcstring ToString();
        virtual void GetSelectorList( GENAPI_NAMESPACE::FeatureList_t &SelectorList, bool Incremental = false );

    protected:
        //! Sets the selector value to the device
        bool SetSelector();

        //! the selecting node 
        CEnumerationPtr m_ptrEnumSelector;

        //! the symbolics available for the enum selector
        NodeList_t m_ptrEntries;

        //! the current value of this "digit"
        NodeList_t::iterator m_itCurrentEntry;

        //! stores the original value of the selector
        int64_t m_OriginalEnumIntValue;

        //! indicates if the digit has changed
        bool m_DigitHasChanged;
    };

    //-------------------------------------------------

    //! A selector set counter digit formed by an integer
    class CIntSelectorDigit : public ISelectorDigit
    {
    public:
        //! Constructor
        CIntSelectorDigit( 
            IBase *pBase //!> Node covered by this digit
            );

        // Implementation of ISelectorDigit
    public:
        virtual bool SetFirst();
        virtual bool SetNext(bool Tick = true);
        virtual void Restore();
        virtual GENICAM_NAMESPACE::gcstring ToString();
        virtual void GetSelectorList( GENAPI_NAMESPACE::FeatureList_t &SelectorList, bool Incremental = false );

    protected:
        //! the selecting node 
        CIntegerPtr m_ptrIntSelector;

        //! the current value of this "digit"
        int64_t m_CurrentValue;

        //! stores the original value of the selector
        int64_t m_OriginalIntValue;

        //! indicates if the digit has changed
        bool m_DigitHasChanged;
    };

}
#endif

