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

#ifndef GENAPI_SELECTORSET_H
#define GENAPI_SELECTORSET_H

#include <GenApi/GenApiDll.h>
#include <GenApi/ISelectorDigit.h>
#include <GenApi/IBase.h>
#include <GenApi/Pointer.h>

namespace GENAPI_NAMESPACE
{

    //! The set of selectors selecting a given node
    class GENAPI_DECL CSelectorSet : public ISelectorDigit
    {
    public:
        //! Constructor
        CSelectorSet ( 
            IBase *pBase //!> Feature selected by the selector set 
            );

        //! Destructor
        virtual ~CSelectorSet();

        //! returns true if no selectors are present
        bool IsEmpty();


        // Implementation of ISelectorDigit
    public:
        virtual bool SetFirst();
        virtual bool SetNext(bool Tick = true);
        virtual void Restore();
        virtual GENICAM_NAMESPACE::gcstring ToString();
        virtual void GetSelectorList( GENAPI_NAMESPACE::FeatureList_t &SelectorList, bool Incremental = false );

    private:
        struct SelectorIteratorList_t;
        //! List of selector digits
        SelectorIteratorList_t *m_pSelectorIterators;

        //! recursively explores the selectors and sub selectors of a node
        void ExploreSelector( 
            CNodePtr &ptrNode, //!> The node to explore
            NodeList_t &SelectorNodes //!> ordered list of elector names (LSB first, MSB last)
            );

        //! Creates the selector counter
        void Create( 
            IBase* pBase //!> the node to create the selector set for
            );
    };

}
#endif

