<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-layout-sider
    v-model:collapsed="collapsed"
    :width="232"
    :collapsed-width="72"
    breakpoint="lg"
    class="sider-container"
  >
    <div class="brand-wrap">
      <div class="brand-icon"><ControlOutlined /></div>
      <div v-if="!collapsed" class="brand-text">
        <strong>{{ $t("console.title") }}</strong>
        <span>Data Intelligence</span>
      </div>
    </div>
    <a-menu
      mode="inline"
      :selectedKeys="[currentPage]"
      class="menu-container"
      @click="handleMenuChange"
    >
      <a-menu-item-group
        v-for="group in menuList"
        :key="group.key"
        :title="$t(`console.${group.key}`)"
      >
        <a-menu-item v-for="item in group.children" :key="item.key">
          <template #icon><component :is="item.icon" /></template>
          <span>{{ $t(`console.${item.key}`) }}</span>
        </a-menu-item>
      </a-menu-item-group>
    </a-menu>
    <div class="sider-footer">
      <div v-if="!collapsed" class="engine-wrap">
        <a-badge :status="online ? 'success' : 'error'" />
        <span>{{ $t(online ? "console.online" : "console.offline") }}</span>
        <span class="engine-label">ENGINE</span>
      </div>
      <a-tooltip :title="$t(online ? 'console.online' : 'console.offline')">
        <span v-if="collapsed" class="engine-status-collapsed">
          <a-badge :status="online ? 'success' : 'error'" />
        </span>
      </a-tooltip>
      <a-tooltip
        placement="right"
        :title="
          $t(collapsed ? 'common.expandSidebar' : 'common.collapseSidebar')
        "
      >
        <a-button
          class="sider-toggle"
          :aria-label="
            $t(collapsed ? 'common.expandSidebar' : 'common.collapseSidebar')
          "
          @click="handleToggleSidebar"
        >
          <MenuUnfoldOutlined v-if="collapsed" />
          <MenuFoldOutlined v-else />
        </a-button>
      </a-tooltip>
    </div>
  </a-layout-sider>
</template>

<script lang="ts" setup name="ConsoleSidebar">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { MenuProps } from "ant-design-vue";
import {
  AppstoreOutlined,
  ApartmentOutlined,
  CloudServerOutlined,
  ControlOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  FileOutlined,
  MessageOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  NodeIndexOutlined,
  SearchOutlined,
} from "@ant-design/icons-vue";

defineProps<{ online: boolean }>();
const route = useRoute();
const router = useRouter();
const collapsed = ref(false);
const currentPage = computed(() => String(route.meta.consolePage));
const handleToggleSidebar = () => {
  collapsed.value = !collapsed.value;
};
const handleMenuChange: MenuProps["onClick"] = ({ key }) => {
  router.push(`/${key}`);
};
const menuList = [
  {
    key: "workspace",
    children: [
      { key: "libraries", icon: AppstoreOutlined },
      { key: "assets", icon: FileOutlined },
      { key: "pools", icon: ApartmentOutlined },
      { key: "sources", icon: DeploymentUnitOutlined },
      { key: "canvas", icon: NodeIndexOutlined },
    ],
  },
  {
    key: "infrastructure",
    children: [
      { key: "databases", icon: DatabaseOutlined },
      { key: "models", icon: CloudServerOutlined },
    ],
  },
  {
    key: "playground",
    children: [
      { key: "retrieve", icon: SearchOutlined },
      { key: "chat", icon: MessageOutlined },
    ],
  },
];
</script>

<style scoped lang="less">
.sider-container {
  background: var(--bg-content-color);
  border-right: 1px solid var(--border-main-color);
  box-shadow: 2px 0 12px
    color-mix(in srgb, var(--font-main-color) 4%, transparent);
  transition: width 0.2s ease;
  :deep(.intel-layout-sider-children) {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    overflow: hidden;
  }
  &.intel-layout-sider-collapsed {
    .brand-wrap {
      justify-content: center;
      padding: 16px 0;
    }
    .sider-footer {
      flex-direction: column;
      justify-content: center;
      gap: 8px;
      padding: 12px 0;
    }
    .engine-status-collapsed {
      height: 8px;
    }
    .menu-container {
      :deep(.intel-menu-item-group-list .intel-menu-item) {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 44px;
        margin: 4px auto;
        padding-inline: 0;
      }
      :deep(.intel-menu-item .intel-menu-item-icon) {
        margin: 0;
        line-height: 1;
      }
      :deep(
        .intel-menu-item-group-list .intel-menu-item .intel-menu-title-content
      ) {
        display: none;
      }
      :deep(.intel-menu-item-group + .intel-menu-item-group) {
        margin-top: 12px;
      }
    }
  }
}
.brand-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 88px;
  padding: 20px;
  flex-shrink: 0;
}
.brand-icon {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border-radius: 10px;
  background: var(--bg-blue-color);
  color: var(--color-white);
  font-size: 19px;
  box-shadow: 0 4px 10px
    color-mix(in srgb, var(--color-primary-second) 22%, transparent);
}
.brand-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  white-space: nowrap;
  strong {
    color: var(--font-main-color);
    font-size: 15px;
  }
  span {
    font-size: 11px;
    color: var(--font-info-color);
    letter-spacing: 1px;
  }
}
.menu-container {
  &.intel-menu-inline-collapsed :deep(.intel-menu-item-group-title) {
    display: none;
  }
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  border: 0;
  background: transparent;
  :deep(.intel-menu-item-group-title) {
    font-size: 11px;
    padding: 18px 24px 7px;
    letter-spacing: 0.7px;
    color: var(--font-info-color);
    font-weight: 600;
    text-transform: uppercase;
  }
  :deep(.intel-menu-item) {
    position: relative;
    margin: 3px 12px;
    width: calc(100% - 24px);
    height: 42px;
    line-height: 42px;
    border-radius: 8px;
    color: var(--font-text-color);
    transition:
      color 0.15s ease,
      background 0.15s ease;
    &:hover {
      color: var(--color-primary-second);
      background: color-mix(
        in srgb,
        var(--color-primary-second) 6%,
        var(--bg-content-color)
      );
    }
  }
  :deep(.intel-menu-item-selected) {
    color: var(--color-primary-second);
    font-weight: 600;
    background: color-mix(
      in srgb,
      var(--color-primary-second) 10%,
      var(--bg-content-color)
    );
    &::before {
      position: absolute;
      top: 9px;
      bottom: 9px;
      left: 0;
      width: 3px;
      border-radius: 0 3px 3px 0;
      background: var(--color-primary-second);
      content: "";
    }
  }
  :deep(.intel-menu-item .intel-menu-item-icon) {
    font-size: 17px;
  }
}
.sider-footer {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  min-height: 64px;
  padding: 10px 16px;
  border-top: 1px solid var(--border-main-color);
  background: color-mix(
    in srgb,
    var(--bg-card-color) 40%,
    var(--bg-content-color)
  );
  .sider-toggle {
    display: grid;
    place-items: center;
    width: 36px;
    height: 36px;
    padding: 0;
    border: 1px solid var(--border-main-color);
    border-radius: 9px;
    color: var(--font-info-color);
    &:hover {
      border-color: var(--color-primary-second);
      color: var(--color-primary-second);
      background: var(--bg-content-color);
    }
  }
}
.engine-status-collapsed {
  display: grid;
  place-items: center;
  width: 8px;
  height: 36px;
}
.engine-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--font-text-color);
}
.engine-label {
  margin-left: 8px;
  font-size: 10px;
  color: var(--font-info-color);
  letter-spacing: 1px;
}
</style>
