//-----------------------------------------------------------------------------
//  (c) 2015 by Baumer
//  Project:  GenApi
//    Author:  Thomas Doering
//             Adapted from EventAdapterU3V.h
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
\brief    Declaration of the CEventAdapterCL class.
*/

#ifndef GENAPI_EVENTADAPTERCL_H
#define GENAPI_EVENTADAPTERCL_H

#include <GenApi/EventAdapter.h>

namespace GENAPI_NAMESPACE
{

    /* ------------------------------------------- */
    // Declaration of CL / GenCP Event message structures

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

    //! CL/GenCP command header
    typedef struct PACK_STRUCT CL_COMMAND_HEADER
    {
        // prefix
        uint16_t Preamble;
        uint16_t CcdCrc16;
        uint16_t ScdCrc16;
        uint16_t ChannelId;

        // CCD
        uint16_t Flags;
        uint16_t CommandId;
        uint16_t Length;
        uint16_t ReqId;
    } CL_COMMAND_HEADER;

    //! CL/GenCP EVENT_CMD specific command data WITHOUT event specific data
    typedef struct PACK_STRUCT CL_EVENT_DATA
    {
        // SCD
        uint16_t ReservedOrEventSize;
        uint16_t EventId;
        uint64_t Timestamp;
    } CL_EVENT_DATA;

    //! CL/GenCP EVENT_CMD specific command data WITH event specific data
    typedef struct PACK_STRUCT CL_EVENT_DATA1
    {
        // SCD
        uint16_t ReservedOrEventSize;
        uint16_t EventId;
        uint64_t Timestamp;
        uint8_t  Data[1];
    } CL_EVENT_DATA1;

    //! Entire event data message
    typedef struct PACK_STRUCT CL_EVENT_MESSAGE
    {
        CL_COMMAND_HEADER CommandHeader;
        union {
            CL_EVENT_DATA     EventData;
//          CL_EVENT_DATA1    EventData1;
        };
    } CL_EVENT_MESSAGE;

    const uint16_t CL_EVENT_PREAMBLE = 0x0100;
    const uint16_t CL_EVENT_CMD_ID = 0x0C00;
    const size_t CL_COMMAND_HEADER_SIZE = sizeof (CL_COMMAND_HEADER);
    const size_t CL_EVENT_BASIC_SIZE = sizeof (CL_EVENT_MESSAGE);

    // restore the previous packing
#pragma pack(pop)
    /* ------------------------------------------- */


    //! Connects a U3V Event to a node map
    class GENAPI_DECL CEventAdapterCL : public  CEventAdapter
    {
    public:
        //! Constructor
        CEventAdapterCL(INodeMap* pNodeMap = NULL);

        //! Destructor
        virtual ~CEventAdapterCL();

        virtual void DeliverMessage( const uint8_t msg[], uint32_t numBytes );

        //! Delivers the Event + Data listed in the packet
        void DeliverEventData(const CL_EVENT_DATA *pEventData, uint16_t length);

    };
}

#endif // GENAPI_EVENTADAPTERCL_H
