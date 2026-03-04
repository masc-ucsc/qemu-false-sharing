/*
 *  exit support for qemu
 *
 *  Copyright (c) 2018 Alex Bennée <alex.bennee@linaro.org>
 *
 *  This program is free software; you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation; either version 2 of the License, or
 *  (at your option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with this program; if not, see <http://www.gnu.org/licenses/>.
 */
#include "qemu/osdep.h"
#include "tcg/perf.h"
#include "gdbstub/syscalls.h"
#include "qemu.h"
#include "user-internals.h"
#include "qemu/plugin.h"

#ifdef CONFIG_GCOV
extern void __gcov_dump(void);
#endif

/* Defined in target/riscv/op_helper.c — dump false sharing summary */
extern void riscv_fs_dump_summary(void);

void preexit_cleanup(CPUArchState *env, int code)
{
#ifdef CONFIG_GCOV
        __gcov_dump();
#endif
        /* Dump aggregated false sharing stats before exit.
         * Must happen here because linux-user uses _exit() which
         * bypasses atexit handlers. */
        riscv_fs_dump_summary();

        gdb_exit(code);
        qemu_plugin_user_exit();
        perf_exit();
}
