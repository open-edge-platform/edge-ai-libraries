//-----------------------------------------------------------------------------
//  (c) 2006 by Leutron Vision
//  Project:  GenApi
//    Author:  Jan Becvar
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
/**
\file
\brief    Declaration of the CEventAdapterGEV class.
*/

#ifndef GENAPI_EVENTADAPTERGENERIC_H
#define GENAPI_EVENTADAPTERGENERIC_H

#include <GenApi/EventAdapter.h>

namespace GENAPI_NAMESPACE
{
    //! Connects a generic event to a node map
    class GENAPI_DECL CEventAdapterGeneric : public  CEventAdapter
    {
    public:
        //! Constructor
        CEventAdapterGeneric(INodeMap* pNodeMap = NULL);

        //! Destructor
        virtual ~CEventAdapterGeneric();

        // Does not have implementation, use the version with EventID
        virtual void DeliverMessage( const uint8_t msg[], uint32_t numBytes ); 

        virtual void DeliverMessage( const uint8_t msg[], uint32_t numBytes, const GENICAM_NAMESPACE::gcstring& EventID);

        virtual void DeliverMessage( const uint8_t msg[], uint32_t numBytes, uint64_t EventID);
    private:
        //! Binary version of the EventID
        uint8_t *m_pEventIDBuffer;

        //! Length of the EventID buffer
        int m_AllocEventIDLength;

    };
}

#endif // GENAPI_EVENTADAPTERGENERIC_H
