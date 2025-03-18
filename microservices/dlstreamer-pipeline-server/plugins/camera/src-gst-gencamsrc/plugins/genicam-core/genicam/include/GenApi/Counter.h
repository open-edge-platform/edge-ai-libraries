//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Alexander Happe
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
\brief    Definition of a simple Counter class
\ingroup GenApi_PublicImpl
*/

#ifndef GENAPI_COUNTER_H
#define GENAPI_COUNTER_H

namespace GENAPI_NAMESPACE {

    class Counter
    {
    public:
        Counter() : m_value(0)
        {
        }

        unsigned int GetValue() const
            { return m_value; }

        unsigned int operator++() // prefix
        {
            return ++m_value;
        }

        unsigned int operator++(int) // postfix
        {
            return m_value++;
        }

        unsigned int operator--(int) // postfix
        {
            assert( m_value > 0);
            return m_value--;
        }

        unsigned int operator--() // prefix
        {
            assert( m_value > 0);
            return --m_value;
        }

        operator unsigned int()
        {
            return m_value;
        }

        bool IsZero()
        {
            return m_value == 0;
        }

    private:
        unsigned int m_value;
    };
}

#endif // GENAPI_COUNTER_H

