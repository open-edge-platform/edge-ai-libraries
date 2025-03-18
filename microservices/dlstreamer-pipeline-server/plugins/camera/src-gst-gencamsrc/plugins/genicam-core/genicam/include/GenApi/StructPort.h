//-----------------------------------------------------------------------------
//  (c) 2009 by Basler Vision Technologies
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


#ifndef __STRUCTPORT_H
#define __STRUCTPORT_H

#include <cstring>
#include <string.h>
#include <GenApi/PortImpl.h>

namespace GENAPI_NAMESPACE
{
    //! Implements a register spaces based on a C++ struct
    template <class CDataStruct>
    class CTestPortStruct : public CDataStruct, public GENAPI_NAMESPACE::CPortImpl
    {
    public:
        CTestPortStruct(int64_t BaseAddress = 0)
            : m_BaseAddress(BaseAddress)
        {
            MemSet(0);
            ResetStatistics();
        }

        //-------------------------------------------------------------
        // IBase implementation
        //-------------------------------------------------------------

        //! Get the access mode of the node
        virtual GENAPI_NAMESPACE::EAccessMode GetAccessMode() const
        {
            return RW;
        }

        //! Get the type of the main interface of a node
        virtual GENAPI_NAMESPACE::EInterfaceType GetPrincipalInterfaceType() const
        {
            return intfIPort;
        }

        //---------------------------------------------------------------
        // IPort implementation
        //---------------------------------------------------------------

        //! Reads a chunk of bytes from the port
        virtual void Read(void *pBuffer, int64_t Address, int64_t Length)
        {
            int64_t InternalAddress = Address - m_BaseAddress;

            CDataStruct *pDataStruct = static_cast<CDataStruct*>(this);
            if( InternalAddress < 0 || Length < 0 || InternalAddress + Length > sizeof(CDataStruct) )
                throw RUNTIME_EXCEPTION("CTestPortStruct::Read - Invalid address and/or length");
            memcpy( pBuffer, (uint8_t*)pDataStruct + InternalAddress, (size_t)Length );
            m_NumReads++;
        }

        //! Writes a chunk of bytes to the port
        virtual void Write(const void *pBuffer, int64_t Address, int64_t Length)
        {
            int64_t InternalAddress = Address - m_BaseAddress;

            CDataStruct *pDataStruct = static_cast<CDataStruct*>(this);
            if( InternalAddress < 0 || Length < 0 || InternalAddress + Length > sizeof(CDataStruct) )
                throw RUNTIME_EXCEPTION("CTestPortStruct::Write - Invalid address and/or length");
            memcpy( (uint8_t*)pDataStruct + InternalAddress, pBuffer, (size_t)Length );
            m_NumWrites++;
        }

        //-------------------------------------------------------------
        // Utility functions
        //-------------------------------------------------------------

        void MemSet( const char FillValue )
        {
             memset( static_cast<CDataStruct*>(this), FillValue, sizeof(CDataStruct) );
        }

        //-------------------------------------------------------------
        // Statistics functions
        //-------------------------------------------------------------

        //! Resets the read/write statistics
        void ResetStatistics()
        {
            m_NumReads = 0;
            m_NumWrites = 0;
        }

        //! Returns the number of reads since lastReset Statistics
        int64_t GetNumReads()
        {
            return m_NumReads;
        }

        //! Returns the number of writes since lastReset Statistics
        int64_t GetNumWrites()
        {
            return m_NumWrites;
        }

    protected:
        //! Number of reads since last reset
        int64_t m_NumReads;

        //! Number of writes since last reset
        int64_t m_NumWrites;

        //! the base address used for the struct
        int64_t m_BaseAddress;
    };
}

#endif // __STRUCTPORT_H
