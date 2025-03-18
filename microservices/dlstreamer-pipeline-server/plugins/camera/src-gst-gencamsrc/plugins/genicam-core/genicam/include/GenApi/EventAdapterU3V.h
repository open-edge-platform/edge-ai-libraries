//-----------------------------------------------------------------------------
//  (c) 2013 by Groget
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
\brief    Declaration of the CEventAdapterU3V class.
*/

#ifndef GENAPI_EVENTADAPTERU3V_H
#define GENAPI_EVENTADAPTERU3V_H

#include <GenApi/EventAdapter.h>

namespace GENAPI_NAMESPACE
{

    /* ------------------------------------------- */
    // Declaration of USB3 Vision / GenCP Event message structures

    // some useful macros
    #if defined( _MSC_VER )
        #define PACK_STRUCT
    #elif defined (__GNUC__)
        // While gcc-4 understands #pragma pack,
        // gcc-3 does not
        #define PACK_STRUCT __attribute__((packed))
    #else
    #   error Unknown platform
    #endif

    // make sure everything is properly packed
#pragma pack(push, 1)

    //! U3V/GenCP command header
    typedef struct PACK_STRUCT U3V_COMMAND_HEADER
    {
        uint32_t  Prefix;
        // CCD
        uint16_t Flags;
        uint16_t CommandId;
        uint16_t Length;
        uint16_t ReqId;
    } U3V_COMMAND_HEADER;
    //! U3V/GenCP EVENT_CMD specific command data
    typedef struct PACK_STRUCT U3V_EVENT_DATA
    {
        // SCD
        uint16_t Reserved;
        uint16_t EventId;
        uint64_t Timestamp;
        // Deliberately not mentioning the (optional?) variable sized data 
    } U3V_EVENT_DATA;
    //! Entire event data message (without the variable-sized data field)
    typedef struct PACK_STRUCT U3V_EVENT_MESSAGE
    {
      U3V_COMMAND_HEADER CommandHeader;
      U3V_EVENT_DATA EventData;
    } U3V_EVENT_MESSAGE;

    const uint32_t U3V_EVENT_PREFIX = 0x45563355;
    const uint16_t GENCP_EVENT_CMD_ID = 0x0C00;
    const size_t GENCP_COMMAND_HEADER_SIZE = sizeof (U3V_COMMAND_HEADER);
    const size_t GENCP_EVENT_BASIC_SIZE = sizeof (U3V_EVENT_MESSAGE);

    // restore the previous packing
#pragma pack(pop)
    /* ------------------------------------------- */


    //! Connects a U3V Event to a node map
    class GENAPI_DECL CEventAdapterU3V : public  CEventAdapter
    {
    public:
        //! Constructor
        CEventAdapterU3V(INodeMap* pNodeMap = NULL);

        //! Destructor
        virtual ~CEventAdapterU3V();

        virtual void DeliverMessage( const uint8_t msg[], uint32_t numBytes );

        //! Delivers the Event + Data listed in the packet
        void DeliverEventMessage(const U3V_EVENT_MESSAGE *pEventMessage);

    };
}

#endif // GENAPI_EVENTADAPTERU3V_H
